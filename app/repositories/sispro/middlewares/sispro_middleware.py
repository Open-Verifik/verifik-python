from datetime import datetime

from fastapi import Request

from app.core.http_handler import ApiError

DOCUMENT_TYPES = {"CC", "CE", "PA", "PE"}
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
    date = query.get("date")

    if not document_type:
        raise ApiError("409:documentType is required", code="MissingParameter")

    if document_type not in DOCUMENT_TYPES:
        raise ApiError("409:documentType must be one of CC, CE, PA, PE", code="MissingParameter")

    if not document_number or len(document_number) < 5:
        raise ApiError("409:documentNumber is required", code="MissingParameter")

    if not date:
        raise ApiError("409:date is required", code="MissingParameter")

    try:
        datetime.strptime(date, "%d/%m/%Y")
    except ValueError as exception:
        raise ApiError("409:date must be DD/MM/YYYY", code="MissingParameter") from exception

    request_type = query.get("type")
    if request_type and request_type not in REQUEST_TYPES:
        raise ApiError("409:type must be sync or queue", code="MissingParameter")

    request.state.params = dict(query)
