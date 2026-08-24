from fastapi import APIRouter, Depends

from app.repositories.health.controllers import health_controller as Controller
from app.repositories.health.middlewares import health_middleware as Middleware
from app.repositories.health.models.health_model import HealthStatus


def register(router: APIRouter) -> None:
    router.add_api_route(
        "/health",
        Controller.get,
        methods=["GET"],
        response_model=HealthStatus,
        tags=["health"],
        dependencies=[Depends(Middleware.require_settings)],
    )
