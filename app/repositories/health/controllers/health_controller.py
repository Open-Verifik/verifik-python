from app.core import http_handler as HttpHandler
from app.repositories.health.models.health_model import HealthStatus
from app.repositories.health.modules import health_module as Module


def get() -> HealthStatus:
    try:
        return Module.get()
    except Exception as exception:
        return HttpHandler.to_response(HttpHandler.error_handler(exception))
