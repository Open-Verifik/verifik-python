from app.core.http_handler import ApiError, error_handler
from app.repositories.sispro.modules import sispro_module, smart_batch_module


def process_next(authorization: str) -> None:
    while True:
        claimed = smart_batch_module.claim_next(authorization)
        if not claimed:
            return

        execute_and_record(authorization, claimed)


def execute_and_record(authorization: str, claimed: dict) -> None:
    params = claimed.get("inputData") or {}

    try:
        status, body = sispro_module.get(params, authorization)
    except ApiError as exception:
        handled = error_handler(exception)
        post_failure(claimed, authorization, handled.status, handled.code, handled.message)
        return

    if status == 200:
        post_success(claimed, authorization, body)
        return

    code = body.get("code") if isinstance(body, dict) else None
    message = body.get("message") if isinstance(body, dict) else None
    post_failure(claimed, authorization, status, code, message)


def post_success(claimed: dict, authorization: str, body: dict) -> None:
    smart_batch_module.append_attempt(
        str(claimed["batchId"]),
        int(claimed.get("rowIndex") or 0),
        {"status": "completed", "statusCode": 200, "results": {"1": body.get("data", body)}},
        authorization,
    )


def post_failure(
    claimed: dict,
    authorization: str,
    status_code: int,
    code: str | None,
    message: str | None,
) -> None:
    error_code = code or "Error"
    error_message = message or ""
    smart_batch_module.append_attempt(
        str(claimed["batchId"]),
        int(claimed.get("rowIndex") or 0),
        {
            "status": "failed",
            "statusCode": status_code,
            "code": error_code,
            "message": error_message,
            "errors": [{"step": 1, "code": error_code, "message": error_message}],
        },
        authorization,
    )
