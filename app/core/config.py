from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """App settings loaded from environment variables and the repo .env file."""

    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    app_name: str = "verifik-smartcheck"
    app_env: str = "development"
    port: int = 8000
    verifik_api_url: str = "https://verifik.app"
    verifik_timeout_seconds: float = 125
    verifik_internal_secret: str | None = None
    queue_tick_enabled: bool = True
    queue_tick_seconds: float = 15
    queue_tick_max_rows: int = 10

    @property
    def should_verify_ssl(self) -> bool:
        return self.app_env != "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
