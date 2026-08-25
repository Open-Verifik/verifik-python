import asyncio
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app import routes
from app.core.config import get_settings
from app.core.http_handler import ApiError, error_handler, to_response
from app.repositories.sispro.modules import sispro_queue_worker as QueueWorker


async def queue_tick_loop() -> None:
    settings = get_settings()

    while True:
        await asyncio.sleep(settings.queue_tick_seconds)
        try:
            await asyncio.to_thread(QueueWorker.process_next)
        except Exception:
            continue


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    task = None

    if settings.queue_tick_enabled and settings.verifik_internal_secret:
        task = asyncio.create_task(queue_tick_loop())
        seconds = settings.queue_tick_seconds
        target = settings.verifik_api_url
        print(f"queue tick started every {seconds}s -> {target}", flush=True)

    yield

    if task:
        task.cancel()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(ApiError)
    async def api_error_handler(_request: Request, exception: ApiError):
        return to_response(error_handler(exception))

    api = APIRouter()
    routes.register(api)
    app.include_router(api)

    return app


app = create_app()
