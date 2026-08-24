from app.core.config import get_settings


def require_settings() -> None:
    get_settings()
