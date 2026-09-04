# Async queue (operators)

Customer-facing A–Z lives on Docusaurus:

- [SmartBatch](https://docs.verifik.co/smart-batch)
- [Call endpoints as queue (async)](https://docs.verifik.co/smart-batch/async-queue)

This file is the in-repo operator guide: enqueue path, HMAC claim, lifespan tick, env, and how to run the process on Forge / PM2. Do not copy HMAC, `VERIFIK_INTERNAL_SECRET`, or `/v2/internal/...` into public docs.

## Public vs internal

| Host | Who talks to it |
| --- | --- |
| `https://async.verifik.co` | Customers. Same catalog path, `?type=queue` → `202`. |
| `https://api.verifik.co` | Node. JWT, credits, SmartBatch documents, feature URLs. |
| `https://ai.verifik.co` | Smart-Agent UI. Wizard, dashboard, webhooks. |

Python never verifies JWTs. It forwards `Authorization: Bearer …` to Node. Node is the store.

## Sync vs queue

Every catalog URL from `app-features-final.json` (plus first-class SISPRO and cédula) supports the same switch:

| `type` | Path | Response |
| --- | --- | --- |
| omitted or `sync` | Proxy to Node, wait | Feature body (`200` / `401` / `404` / `409` / `504`) |
| `queue` | Enqueue one-row Smart Batch | `202` `{ status, batchId, rowIndex, attemptCount }` |

`type` must be omitted, `sync`, or `queue`. Controllers strip `type` before they save `inputData`.

## Enqueue path

```
route → middleware → controller → queue_enqueue.enqueue
  → SmartBatchModule.create_from_queue
  → POST /v2/smart-batches/from-queue (customer JWT)
  → BackgroundTasks → QueueWorker.process_next
```

| Product | Controller | Spec |
| --- | --- | --- |
| SISPRO | `app/repositories/sispro/controllers/sispro_controller.py` | `SISPRO_QUEUE` → `co.sispro.queue` / `colombia_api_affiliations` |
| Cédula | `app/repositories/cedula/controllers/cedula_controller.py` | `CEDULA_QUEUE` → `co.cedula.queue` / `colombia_api_identity_lookup` |
| Other catalog URLs | `app/repositories/catalog/catalog_controller.py` | `catalog_queue.queue_spec(feature)` → `{featureCode}.queue` |

`queue_enqueue.py` POSTs the spec + `inputData` to Node, then schedules one `process_next` after the `202`. The customer JWT is **not** stored on the row.

## Tick and claim

`app/main.py` lifespan starts `queue_tick_loop` when `QUEUE_TICK_ENABLED` is true **and** `VERIFIK_INTERNAL_SECRET` is set. There is no cron URL.

Every `QUEUE_TICK_SECONDS` the loop calls `QueueWorker.process_next`, which:

1. **Claim** — `GET /v2/internal/smart-batches/queue/next` with `x-verifik-internal-key` = SHA-256 hex of `VERIFIK_INTERNAL_SECRET` (`smart_batch_module.internal_key`).
2. Node claims the oldest `executor: "queue"` row and **mints a ~300s client JWT** (same idea as FeatureRunner).
3. **Invoke** — `GET`/`POST` the claimed AppFeature `path` with that minted Bearer. Credits bill that client.
4. **Record** — `POST /v2/smart-batches/:id/rows/:rowIndex/attempts` with the minted Bearer. Node fires `notification.webhookUrl` / completion emails on a terminal row or batch.
5. Repeat until claim is empty or `QUEUE_TICK_MAX_ROWS`.

Restart-safe: Mongo holds the row. The next tick mints a new token. We do **not** put JWTs in Redis or Mongo. Stale `processing` rows older than the mint TTL are claimable again if Python died mid-attempt.

Retryable = `429`, `5xx`, or codes `Timeout` / `ServiceUnavailable` / `timeout_database` / `upstream_error`. **Not** `404` or `MissingParameter`.

## Env

From `.env` / `app/core/config.py` (process env wins, then `.env`, then class defaults). Restart uvicorn after changes — `get_settings()` is cached.

| Variable | Role |
| --- | --- |
| `VERIFIK_API_URL` | Node base. Production: `https://api.verifik.co`. Local default: `https://verifik.app`. |
| `VERIFIK_INTERNAL_SECRET` | Shared with Node. Empty → tick does not start. |
| `QUEUE_TICK_ENABLED` | Set `false` in pytest so the lifespan loop does not run. |
| `QUEUE_TICK_SECONDS` | Sleep between ticks (default `15`). |
| `QUEUE_TICK_MAX_ROWS` | Max claims per tick (default `10`). |

The secret on Python and Node **must match**. HMAC middleware on Node rejects a bad key with `Invalid internal queue credentials`.

### Production 401 on the tick

If the tick logs `queue tick skipped: 401` and the body is the public JWT gate (`Protected resource, use Authorization header…`), Node does **not** have the unprotected internal route deployed yet. A secret mismatch would say `Invalid internal queue credentials`. Deploy `smart-batch-internal.routes.js` on the API before expecting claims to succeed.

## PM2 (async.verifik.co)

One **fork**. Do **not** use cluster or `-i 1` (PM2 6 treats `-i` as cluster). Uvicorn is Python — `--interpreter none` so PM2 does not run it with Node.

```bash
pm2 start .venv/bin/python \
  --name async.verifik.co \
  --cwd /home/forge/async.verifik.co \
  --interpreter none \
  -- -m uvicorn app.main:app --host 127.0.0.1 --port 3062
```

If the process already exists, `pm2 restart async.verifik.co`. Then `pm2 save`. Do not touch the Node `PRODUCTION` app on the same box.

Health: `GET http://127.0.0.1:3062/health`. Logs should show `queue tick started every 15s -> https://api.verifik.co` when the secret is set.

## Node pieces

```
verifik-backend/Repositories/SmartBatch/
  models/smart-batch.model.js
  routes/smart-batch-internal.routes.js   # GET /v2/internal/smart-batches/queue/next
  routes/smart-batch.routes.js            # POST /v2/smart-batches/from-queue
  services/enqueue-from-request.service.js
  helpers/queue-internal-auth.helper.js
```

`executor` on the config/batch: `queue` (this worker), `featureRunner` (Node Start / Sync), `browser` (tab only). Smart-Agent labels those **Async** / **Sync**.

## Python pieces

```
app/main.py lifespan
app/repositories/sispro/modules/queue_enqueue.py
app/repositories/sispro/modules/smart_batch_module.py
app/repositories/sispro/modules/sispro_queue_worker.py
app/repositories/catalog/catalog_queue.py
```

Hour / day / total retry caps and Redis / TaskIQ stay later. This pass is per-row `maxRetries` + the in-process tick.

## Local try

```bash
# sync
curl -sS -H "Authorization: Bearer $JWT" \
  "http://localhost:8000/v2/co/afiliaciones?documentType=CC&documentNumber=1007463534&date=09/05/2008"

# queue
curl -sS -H "Authorization: Bearer $JWT" \
  "http://localhost:8000/v2/co/cedula?documentType=CC&documentNumber=1032386359&type=queue"
```

Production customers hit `https://async.verifik.co` with the same paths. Then open Smart-Agent on `batchId`.
