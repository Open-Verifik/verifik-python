from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from app.repositories.home.controllers import home_controller as Controller
from app.repositories.home.middlewares import home_middleware as Middleware


def register(router: APIRouter) -> None:
    router.add_api_route(
        "/",
        Controller.get,
        methods=["GET"],
        response_class=HTMLResponse,
        response_model=None,
        tags=["home"],
        dependencies=[Depends(Middleware.ensure_readme)],
    )
