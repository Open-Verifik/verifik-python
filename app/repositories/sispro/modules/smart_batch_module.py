import hashlib
import re

import httpx

from app.clients.verifik import (
    INTERNAL_KEY_HEADER,
    SMART_BATCH_FROM_QUEUE_PATH,
    SMART_BATCH_INTERNAL_QUEUE_NEXT_PATH,
    get_verifik_client,
)
from app.core.config import get_settings
from app.core.http_handler import ApiError, error_handler

TEMPLATE = re.compile(r"^\{\{\s*([^}]+?)\s*\}\}$")


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


def _is_empty(value) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _get_by_path(source, path):
    if not path or source is None:
        return None

    current = source
    segments = [part for part in str(path).replace("[", ".").replace("]", "").split(".") if part]

    for segment in segments:
        if current is None:
            return None
        if isinstance(current, list):
            try:
                current = current[int(segment)]
            except (ValueError, IndexError):
                return None
            continue
        if not isinstance(current, dict):
            return None
        current = current.get(segment)

    return current


def _wrap_result(payload):
    if not isinstance(payload, dict):
        return {"data": payload}
    if "data" in payload:
        return payload
    return {**payload, "data": payload}


def _resolve_template(value, context):
    if not isinstance(value, str):
        return value
    match = TEMPLATE.match(value)
    if not match:
        return value
    return _get_by_path(context, match.group(1))


def resolve_step_params(step: dict, input_data: dict, results: dict) -> dict:
    context = {
        "input": input_data or {},
        "inputData": input_data or {},
        "results": results or {},
        "steps": {str(key): _wrap_result(payload) for key, payload in (results or {}).items()},
    }
    params: dict = {}

    for dependency in step.get("dependencies") or []:
        field = dependency.get("field")
        if field and dependency.get("default") is not None:
            params[field] = dependency["default"]

    for dependency in step.get("dependencies") or []:
        field = dependency.get("field")
        if not field:
            continue
        raw = _get_by_path(input_data or {}, field)
        if not _is_empty(raw):
            params[field] = raw

    for key, value in (step.get("parameterDefaults") or {}).items():
        resolved = _resolve_template(value, context)
        if not _is_empty(resolved):
            params[key] = resolved

    for input_column, api_param in (step.get("inputFieldMapping") or {}).items():
        if not api_param:
            continue
        raw = (
            _resolve_template(input_column, context)
            if isinstance(input_column, str) and TEMPLATE.match(input_column)
            else _get_by_path(input_data or {}, input_column)
        )
        if not _is_empty(raw):
            params[api_param] = raw

    cleaned = {}
    for key, value in params.items():
        if _is_empty(value):
            continue
        cleaned[key] = value.strip() if isinstance(value, str) else value
    return cleaned


def invoke_path(path: str, method: str, input_data: dict, authorization: str) -> tuple[int, dict]:
    params = {key: value for key, value in (input_data or {}).items() if key != "type"}

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


def invoke_claimed(claimed: dict, authorization: str) -> tuple[int, dict]:
    path = claimed.get("path")
    if not path:
        raise ApiError("503:claimed row is missing path")

    return invoke_path(
        path,
        str(claimed.get("method") or "GET").upper(),
        claimed.get("inputData") or {},
        authorization,
    )


def _step_failure(results: dict, sequence: int, status: int, body: dict) -> dict:
    code = body.get("code") if isinstance(body, dict) else None
    message = body.get("message") if isinstance(body, dict) else None
    error_code = code or "Error"
    error_message = message or ""
    attempt = {
        "status": "partial" if results else "failed",
        "statusCode": status,
        "code": error_code,
        "message": error_message,
        "errors": [{"step": sequence, "code": error_code, "message": error_message}],
    }
    if results:
        attempt["results"] = results
    return attempt


def _has_step_result(results: dict, sequence: int) -> bool:
    if not results:
        return False
    return results.get(sequence) is not None or results.get(str(sequence)) is not None


def _seed_results(claimed: dict) -> dict:
    seeded = {}
    for key, value in (claimed.get("results") or {}).items():
        if value is None:
            continue
        seeded[str(key)] = value
    return seeded


def invoke_claimed_steps(claimed: dict, authorization: str) -> dict:
    steps = claimed.get("steps") or []
    raw_input = claimed.get("rowInput") or claimed.get("inputData") or {}
    results = _seed_results(claimed)

    for index, step in enumerate(steps):
        sequence = int(step.get("sequence") or index + 1)
        path = step.get("path")
        if not path:
            raise ApiError("503:claimed row is missing path")

        if _has_step_result(results, sequence):
            continue

        if results:
            params = resolve_step_params(step, raw_input, results)
        elif index == 0:
            params = claimed.get("inputData") or {}
        else:
            params = resolve_step_params(step, raw_input, results)

        try:
            method = str(step.get("method") or "GET").upper()
            status, body = invoke_path(path, method, params, authorization)
        except ApiError as exception:
            handled = error_handler(exception)
            return _step_failure(
                results,
                sequence,
                handled.status,
                {"code": handled.code, "message": handled.message},
            )

        if status == 200:
            results[str(sequence)] = body.get("data", body)
            continue

        return _step_failure(results, sequence, status, body)

    return {"status": "completed", "statusCode": 200, "results": results}


def claim_next_hmac() -> dict | None:
    return _request(
        "GET",
        SMART_BATCH_INTERNAL_QUEUE_NEXT_PATH,
        extra_headers={INTERNAL_KEY_HEADER: internal_key()},
    ).get("data")


def append_attempt(batch_id: str, row_index: int, attempt: dict, authorization: str) -> dict:
    path = f"/v2/smart-batches/{batch_id}/rows/{row_index}/attempts"
    return _request("POST", path, authorization, json=attempt).get("data") or {}
