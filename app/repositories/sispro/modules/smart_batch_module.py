import httpx

from app.clients.verifik import (
    SMART_BATCH_FROM_QUEUE_PATH,
    SMART_BATCH_QUEUE_NEXT_PATH,
    get_verifik_client,
)
from app.core.http_handler import ApiError


def raise_for_node(status: int, body: object) -> None:
    if status < 400:
        return

    message = ""
    code = None
    if isinstance(body, dict):
        message = body.get("message") or ""
        code = body.get("code")

    detail = f"{status}:{message}" if message else str(status)
    raise ApiError(detail, code=code)


def _request(method: str, path: str, authorization: str, json: dict | None = None) -> dict:
    try:
        with get_verifik_client() as client:
            response = client.request(
                method,
                path,
                json=json,
                headers={"Authorization": authorization},
            )
            body = response.json()
    except httpx.TimeoutException as exception:
        raise ApiError("504") from exception
    except httpx.RequestError as exception:
        raise ApiError(f"503:{exception}") from exception
    except ValueError as exception:
        raise ApiError(f"503:{exception}") from exception

    if not isinstance(body, dict):
        raise ApiError("503")

    raise_for_node(response.status_code, body)
    return body


def create_from_queue(params: dict, authorization: str) -> dict:
    body = _request(
        "POST",
        SMART_BATCH_FROM_QUEUE_PATH,
        authorization,
        json={
            "documentType": params["documentType"],
            "documentNumber": params["documentNumber"],
            "date": params["date"],
        },
    )
    data = body.get("data") or {}

    if not data.get("batchId"):
        raise ApiError("503:queue enqueue did not return batchId")

    return data


def claim_next(authorization: str) -> dict | None:
    return _request("GET", SMART_BATCH_QUEUE_NEXT_PATH, authorization).get("data")


def append_attempt(batch_id: str, row_index: int, attempt: dict, authorization: str) -> dict:
    path = f"/v2/smart-batches/{batch_id}/rows/{row_index}/attempts"
    return _request("POST", path, authorization, json=attempt).get("data") or {}
