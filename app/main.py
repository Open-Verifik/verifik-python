from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app import routes
from app.core.config import get_settings
from app.core.http_handler import ApiError, error_handler, to_response


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0")

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
