from fastapi import BackgroundTasks, Request
from fastapi.responses import JSONResponse
from starlette.responses import Response

from app.core import http_handler as HttpHandler
from app.core.http_handler import ApiError
from app.repositories.catalog import catalog_middleware as Middleware
from app.repositories.catalog import catalog_queue as CatalogQueue
from app.repositories.proxy.modules import proxy_module as Module
from app.repositories.sispro.modules import queue_enqueue as QueueEnqueue


async def collect_values(request: Request) -> dict:
    values = dict(request.query_params)

    if request.method.upper() in {"GET", "HEAD"}:
        return values

    if not request.headers.get("content-type", "").startswith("application/json"):
        return values

    try:
        payload = await request.json()
    except ValueError:
        return values

    if isinstance(payload, dict):
        values.update(payload)

    return values


def enqueue(feature: dict, request: Request, background_tasks: BackgroundTasks) -> JSONResponse:
    params = request.state.params
    data = CatalogQueue.input_data(params)

    return QueueEnqueue.enqueue(
        request.state.authorization,
        CatalogQueue.queue_spec(feature),
        data,
        background_tasks,
        batch_name=CatalogQueue.batch_name(feature, params),
    )


def make_handler(feature: dict):
    async def handle(request: Request, background_tasks: BackgroundTasks) -> Response:
        try:
            values = await collect_values(request)
            Middleware.validate_feature(feature, values)
            request.state.params = values

            if values.get("type") == "queue":
                return enqueue(feature, request, background_tasks)

            payload = CatalogQueue.input_data(values)
            status, body = Module.forward(
                feature["method"],
                feature["url"],
                request.state.authorization,
                payload,
                payload if feature["method"] not in {"GET", "HEAD", "DELETE"} else None,
            )
            return JSONResponse(status_code=status, content=body)
        except ApiError:
            raise
        except Exception as exception:
            return HttpHandler.to_response(HttpHandler.error_handler(exception))

    handle.__name__ = feature["code"]
    handle.__doc__ = feature["name"]
    return handle
