import hashlib

import httpx

from app.clients.verifik import (
    INTERNAL_KEY_HEADER,
    SMART_BATCH_FROM_QUEUE_PATH,
    SMART_BATCH_INTERNAL_QUEUE_NEXT_PATH,
    get_verifik_client,
)
from app.core.config import get_settings
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


def internal_key() -> str:
    secret = get_settings().verifik_internal_secret

    if not secret:
        raise ApiError("503:queue tick is not configured")

    return hashlib.sha256(secret.encode()).hexdigest()


def _request(
    method: str,
    path: str,
    authorization: str | None = None,
    json: dict | None = None,
    extra_headers: dict | None = None,
) -> dict:
    headers = {}
    if authorization:
        headers["Authorization"] = authorization
    if extra_headers:
        headers.update(extra_headers)

    try:
        with get_verifik_client() as client:
            response = client.request(method, path, json=json, headers=headers)
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


def create_from_queue(
    authorization: str,
    spec: dict,
    input_data: dict,
    batch_name: str | None = None,
) -> dict:
    payload = {**spec, "inputData": input_data}
    if batch_name:
        payload["batchName"] = batch_name

    body = _request("POST", SMART_BATCH_FROM_QUEUE_PATH, authorization, json=payload)
    data = body.get("data") or {}

    if not data.get("batchId"):
        raise ApiError("503:queue enqueue did not return batchId")

    return data


def invoke_claimed(claimed: dict, authorization: str) -> tuple[int, dict]:
    path = claimed.get("path")
    if not path:
        raise ApiError("503:claimed row is missing path")

    method = str(claimed.get("method") or "GET").upper()
    input_data = claimed.get("inputData") or {}
    params = {key: value for key, value in input_data.items() if key != "type"}

    try:
        with get_verifik_client() as client:
            kwargs = {"headers": {"Authorization": authorization}}
            if method == "GET":
                kwargs["params"] = params
            else:
                kwargs["json"] = params

            response = client.request(method, path, **kwargs)
            body = response.json()
    except httpx.TimeoutException as exception:
        raise ApiError("504") from exception
    except httpx.RequestError as exception:
        raise ApiError(f"503:{exception}") from exception
    except ValueError as exception:
        raise ApiError(f"503:{exception}") from exception

    if not isinstance(body, dict):
        raise ApiError("503")

    return response.status_code, body


def claim_next_hmac() -> dict | None:
    return _request(
        "GET",
        SMART_BATCH_INTERNAL_QUEUE_NEXT_PATH,
        extra_headers={INTERNAL_KEY_HEADER: internal_key()},
    ).get("data")


def append_attempt(batch_id: str, row_index: int, attempt: dict, authorization: str) -> dict:
    path = f"/v2/smart-batches/{batch_id}/rows/{row_index}/attempts"
    return _request("POST", path, authorization, json=attempt).get("data") or {}
