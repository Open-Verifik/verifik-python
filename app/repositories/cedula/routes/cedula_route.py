from fastapi import APIRouter, Depends

from app.repositories.cedula.controllers import cedula_controller as Controller
from app.repositories.cedula.middlewares import cedula_middleware as Middleware


def register(router: APIRouter) -> None:
    router.add_api_route(
        "/v2/co/cedula",
        Controller.get,
        methods=["GET"],
        response_model=None,
        tags=["cedula"],
        dependencies=[
            Depends(Middleware.require_authorization),
            Depends(Middleware.get_validation),
        ],
    )
