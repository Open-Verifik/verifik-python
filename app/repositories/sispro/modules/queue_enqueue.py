from fastapi.responses import JSONResponse

from app.repositories.sispro.modules import sispro_queue_worker as QueueWorker
from app.repositories.sispro.modules import smart_batch_module as SmartBatchModule


def enqueue(
    authorization: str,
    spec: dict,
    input_data: dict,
    background_tasks,
    batch_name: str | None = None,
):
    data = SmartBatchModule.create_from_queue(
        authorization,
        spec,
        input_data,
        batch_name=batch_name,
    )
    background_tasks.add_task(QueueWorker.process_next, authorization)

    return JSONResponse(
        status_code=202,
        content={
            "status": "queued",
            "batchId": str(data["batchId"]),
            "rowIndex": data.get("rowIndex", 0),
            "attemptCount": data.get("attemptCount", 0),
        },
    )
