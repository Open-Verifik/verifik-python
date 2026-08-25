from fastapi import APIRouter, Depends

from app.repositories.catalog import catalog_controller as Controller
from app.repositories.catalog import catalog_loader
from app.repositories.catalog import catalog_middleware as Middleware


def _openapi_parameters(feature: dict) -> list[dict]:
    parameters = []

    for dep in feature.get("dependencies") or []:
        if not dep.get("field"):
            continue
        schema = {"type": "string"}
        if dep.get("enum"):
            schema["enum"] = dep["enum"]
        parameters.append(
            {
                "name": dep["field"],
                "in": "query",
                "required": bool(dep.get("required")),
                "description": dep.get("description") or "",
                "schema": schema,
            }
        )

    parameters.append(
        {
            "name": "type",
            "in": "query",
            "required": False,
            "description": "sync (default) waits on Node. queue creates a 1-row SmartBatch.",
            "schema": {"type": "string", "enum": ["sync", "queue"]},
        }
    )
    return parameters


def register(router: APIRouter) -> None:
    for feature in catalog_loader.load_catalog():
        router.add_api_route(
            feature["url"],
            Controller.make_handler(feature),
            methods=[feature["method"]],
            name=feature["code"],
            tags=[feature.get("country") or "catalog"],
            response_model=None,
            dependencies=[Depends(Middleware.require_authorization)],
            openapi_extra={"parameters": _openapi_parameters(feature)},
        )
