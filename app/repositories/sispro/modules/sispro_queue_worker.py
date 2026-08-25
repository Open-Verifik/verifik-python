import logging

from app.core.config import get_settings
from app.core.http_handler import ApiError, error_handler
from app.repositories.sispro.modules import smart_batch_module

logger = logging.getLogger("uvicorn.error")


def row_ref(claimed: dict) -> str:
    batch_id = claimed.get("batchId")
    row_index = claimed.get("rowIndex", 0)
    path = claimed.get("path") or "?"
    return f"{batch_id} row {row_index} {path}"


def process_next(_authorization: str | None = None) -> None:
    settings = get_settings()
    processed = 0

    try:
        while processed < settings.queue_tick_max_rows:
            claimed = smart_batch_module.claim_next_hmac()
            if not claimed:
                if processed:
                    logger.info("queue tick ok: finished %s row(s)", processed)
                return

            token = claimed.get("authorization")
            if not token:
                logger.warning("queue tick skipped: claim had no minted JWT")
                return

            logger.info("queue tick claimed %s", row_ref(claimed))
            execute_and_record(token, claimed)
            processed += 1
    except ApiError as exception:
        logger.warning("queue tick skipped: %s", exception)
        return


def execute_and_record(authorization: str, claimed: dict) -> None:
    try:
        status, body = smart_batch_module.invoke_claimed(claimed, authorization)
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
    logger.info("queue tick ok: completed %s", row_ref(claimed))


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
    logger.warning(
        "queue tick recorded failure %s status=%s code=%s",
        row_ref(claimed),
        status_code,
        error_code,
    )
