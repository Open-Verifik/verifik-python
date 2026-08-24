from dataclasses import dataclass

from fastapi.responses import JSONResponse


class ApiError(Exception):
    """Domain error that middleware can raise before the controller runs."""

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.override_code = code

STATUS_MAP = {
    "400": ("BadRequest", "Bad Request"),
    "401": ("Unauthorized", "Unauthorized"),
    "403": ("Forbidden", "Access forbidden"),
    "404": ("NotFound", "Record not found."),
    "409": ("Conflict", "Record conflicts with existing records in place."),
    "410": ("Gone", "This resource is no longer available"),
    "412": ("PreconditionFailed", "Pre condition to create this request, failed"),
    "422": ("UnprocessableEntity", "Record cannot be saved with the current params"),
    "423": ("Locked", "The resource that is being accessed is locked"),
    "451": ("NotFound", "The endpoint does not contain the data requested"),
    "500": ("InternalServerError", "Server error."),
    "503": ("ServiceUnavailable", "Service temporarily unavailable"),
    "504": ("Timeout", "Endpoint timed out, try again later."),
}


@dataclass
class HandledError:
    status: int
    code: str
    message: str


def error_handler(exception: Exception) -> HandledError:
    """Map an exception to {status, code, message}, same idea as Core/http-handler.js."""
    raw = str(exception) or "Internal Server Error"
    status_key, _, detail = raw.partition(":")
    status_key = status_key.strip()
    detail = detail.strip() or None

    if status_key in STATUS_MAP:
        code, default_message = STATUS_MAP[status_key]

        if isinstance(exception, ApiError) and exception.override_code:
            code = exception.override_code

        return HandledError(status=int(status_key), code=code, message=detail or default_message)

    if isinstance(exception, FileNotFoundError):
        return HandledError(status=404, code="NotFound", message="Record not found.")

    return HandledError(status=500, code="InternalServerError", message=raw)


def to_response(error: HandledError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status,
        content={"code": error.code, "message": error.message},
    )
