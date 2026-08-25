import httpx

from app.core.config import get_settings

AFILIACIONES_PATH = "/v2/co/afiliaciones"
CEDULA_PATH = "/v2/co/cedula"
SMART_BATCH_FROM_QUEUE_PATH = "/v2/smart-batches/from-queue"
SMART_BATCH_QUEUE_NEXT_PATH = "/v2/smart-batches/queue/next"
SMART_BATCH_INTERNAL_QUEUE_NEXT_PATH = "/v2/internal/smart-batches/queue/next"
INTERNAL_KEY_HEADER = "x-verifik-internal-key"


def get_verifik_client() -> httpx.Client:
    settings = get_settings()

    return httpx.Client(
        base_url=settings.verifik_api_url.rstrip("/"),
        timeout=settings.verifik_timeout_seconds,
        verify=settings.should_verify_ssl,
        follow_redirects=True,
    )
