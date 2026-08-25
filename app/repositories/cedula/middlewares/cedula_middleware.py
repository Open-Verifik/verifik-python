from fastapi import Request

from app.core.http_handler import ApiError

DOCUMENT_TYPES = {"CC", "PPT"}
REQUEST_TYPES = {"sync", "queue"}


def require_authorization(request: Request) -> None:
    header = request.headers.get("authorization")

    if not header or not header.lower().startswith("bearer "):
        raise ApiError("401")

    if not header[7:].strip():
        raise ApiError("401")

    request.state.authorization = header


def get_validation(request: Request) -> None:
    query = request.query_params
    document_type = query.get("documentType")
    document_number = query.get("documentNumber")

    if not document_type:
        raise ApiError("409:documentType is required", code="MissingParameter")

    if document_type not in DOCUMENT_TYPES:
        raise ApiError("409:documentType must be one of CC, PPT", code="MissingParameter")

    if not document_number or len(document_number) < 5:
        raise ApiError("409:documentNumber is required", code="MissingParameter")

    if len(document_number) > 10:
        raise ApiError("409:documentNumber must be at most 10 characters", code="MissingParameter")

    request_type = query.get("type")
    if request_type and request_type not in REQUEST_TYPES:
        raise ApiError("409:type must be sync or queue", code="MissingParameter")

    request.state.params = dict(query)
