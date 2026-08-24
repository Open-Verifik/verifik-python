from fastapi import APIRouter, Depends

from app.repositories.sispro.controllers import sispro_controller as Controller
from app.repositories.sispro.middlewares import sispro_middleware as Middleware


def register(router: APIRouter) -> None:
    router.add_api_route(
        "/v2/co/afiliaciones",
        Controller.get,
        methods=["GET"],
        response_model=None,
        tags=["sispro"],
        dependencies=[
            Depends(Middleware.require_authorization),
            Depends(Middleware.get_validation),
        ],
    )
