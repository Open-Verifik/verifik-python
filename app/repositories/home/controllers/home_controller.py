from fastapi.responses import HTMLResponse
from starlette.responses import Response

from app.core import http_handler as HttpHandler
from app.repositories.home.modules import home_module as Module


def get() -> Response:
    try:
        page = Module.render()

        return HTMLResponse(content=page.html)
    except Exception as exception:
        return HttpHandler.to_response(HttpHandler.error_handler(exception))
