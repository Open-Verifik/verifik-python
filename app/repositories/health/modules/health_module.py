from app.core.config import get_settings
from app.repositories.health.models.health_model import HealthStatus


def get() -> HealthStatus:
    settings = get_settings()

    return HealthStatus(status="ok", service=settings.app_name)
