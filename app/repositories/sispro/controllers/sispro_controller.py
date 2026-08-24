from typing import Annotated

from fastapi import BackgroundTasks, Depends, Query, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from starlette.responses import Response

from app.core import http_handler as HttpHandler
from app.core.http_handler import ApiError
from app.core.security import bearer_scheme
from app.repositories.sispro.modules import sispro_module as Module
from app.repositories.sispro.modules import sispro_queue_worker as QueueWorker
from app.repositories.sispro.modules import smart_batch_module as SmartBatchModule


def get(
    request: Request,
    background_tasks: BackgroundTasks,
    documentType: Annotated[str, Query(description="CC, CE, PA, or PE")],
    documentNumber: Annotated[str, Query(min_length=5)],
    date: Annotated[str, Query(description="DD/MM/YYYY")],
    force: Annotated[bool | None, Query()] = None,
    audit: Annotated[bool | None, Query()] = None,
    type: Annotated[
        str | None,
        Query(description="sync (default) waits on SISPRO. queue creates a 1-row SmartBatch."),
    ] = None,
    _credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> Response:
    try:
        if request.state.params.get("type") == "queue":
            return enqueue(request, background_tasks)

        status, body = Module.get(request.state.params, request.state.authorization)

        return JSONResponse(status_code=status, content=body)
    except ApiError:
        raise
    except Exception as exception:
        return HttpHandler.to_response(HttpHandler.error_handler(exception))


def enqueue(request: Request, background_tasks: BackgroundTasks) -> JSONResponse:
    data = SmartBatchModule.create_from_queue(request.state.params, request.state.authorization)
    background_tasks.add_task(QueueWorker.process_next, request.state.authorization)

    return JSONResponse(
        status_code=202,
        content={
            "status": "queued",
            "batchId": str(data["batchId"]),
            "rowIndex": data.get("rowIndex", 0),
            "attemptCount": data.get("attemptCount", 0),
        },
    )
