# verifik-smartcheck

FastAPI service in front of `verifik-backend`. Home and health are the scaffold. SISPRO is the first product: **sync proxy** by default, **queue** when `?type=queue`.

Python never verifies JWTs. It forwards `Authorization: Bearer …` to Node. Node stays the store (credits, `APIRequest`, SmartBatch). Python is the public facade — and, for queue, the unattended Smart-Agent tab.

## Node → Python

| Node (`verifik-backend`) | This repo |
| --- | --- |
| `package.json` / `npm install` | `pyproject.toml` / `pip install -e ".[dev]"` |
| `.env` + `Core/config.js` | `.env` + `app/core/config.py` |
| `Core/http-handler.js` | `app/core/http_handler.py` |
| Koa + `app.listen` | FastAPI + `uvicorn` |
| `Routes/unprotected-repositories.js` | `app/routes.py` |
| `Repositories/Home/routes/home.route.js` | `app/repositories/home/routes/home_route.py` |
| `try { } catch (exception)` | `try: except Exception as exception:` |
| ESLint / Jest / nodemon | Ruff / pytest / `uvicorn --reload` |

Python cannot name a file `home.route.py` (the extra dot breaks imports), so we use `home_route.py`.

`.env` is the env-vars file (dotenv). `.venv/` is the virtualenv folder. Do not run `python3 -m venv .env`.

## Setup

Python 3.12+.

```bash
cd verifik-python
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

## Run

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

- Home (this README as HTML): http://localhost:8000/
- Health: http://localhost:8000/health
- SISPRO (proxies Node): http://localhost:8000/v2/co/afiliaciones
- Swagger: http://localhost:8000/docs

`VERIFIK_API_URL` comes from `.env` (see `app/core/config.py`). Process env wins, then `.env`, then the class default `https://verifik.app`. Pass the same `Authorization: Bearer <jwt>` header Company A already uses on Node. Python does not have a JWT secret. After you change `.env`, restart uvicorn — `get_settings()` is cached.

`GET /` is declared in `home_route.py` as `add_api_route("/", ...)`, not by the function name `get`. FastAPI 404s unknown paths as `{"detail": "Not Found"}`.

## Test

```bash
source .venv/bin/activate
pytest
ruff check .
```

## Repository pattern

Same chain as Koa: **route → middleware → controller → module → model**.

```
app/
  main.py                                  # FastAPI app
  routes.py                                # registers each repository
  core/
    config.py                              # env settings
    http_handler.py                        # status → {code, message}
  repositories/home/
    routes/home_route.py                   # PATH + Depends(middleware) + controller
    middlewares/home_middleware.py
    controllers/home_controller.py         # try / except → HttpHandler
    modules/home_module.py                 # business logic
    models/home_model.py                   # Pydantic shape (not Mongo yet)
  repositories/health/                     # same five files
  repositories/sispro/                     # GET /v2/co/afiliaciones (sync + queue)
    modules/sispro_module.py               # sync GET → Node SISPRO
    modules/smart_batch_module.py          # Node SmartBatch HTTP (enqueue / claim / attempt)
    modules/sispro_queue_worker.py         # open-tab loop: claim → SISPRO → POST attempt
  clients/verifik.py                       # httpx client (forwards Authorization)
  workers/                                 # later: Redis / TaskIQ when this loop is too small
  policies/                                # later: hour / day / total retry budgets
tests/
```

Koa:

```js
router.get(`${PATH}`, Middleware.ensureReadme, Controller.get);
```

FastAPI (in the route file):

```python
router.add_api_route(
    "/",
    Controller.get,
    methods=["GET"],
    dependencies=[Depends(Middleware.ensure_readme)],
)
```

Controllers catch errors the same way as Node. `HttpHandler.error_handler` understands `401`, `404`, `409`, `412`, … and prefixed messages (`raise ApiError("412:missing_otp")`). Middleware that runs as `Depends` raises `ApiError` so the response stays `{code, message}` (not FastAPI’s `{"detail": ...}`).

SISPRO query matches Node Joi: `documentType` (`CC|CE|PA|PE`), `documentNumber` (min 5), `date` (`DD/MM/YYYY`), optional `force` / `audit` / `type`. Missing/invalid query is `409` + `MissingParameter`. Node’s own 200/401/404/409 body is returned as-is. Timeout is `504`; Node unreachable is `503`.

Every folder that we import from has an empty `__init__.py`. That only marks the directory as a Python package (`require("../controllers/x")` does not need this; `from app.repositories.home.routes import home_route` does).

---

## Tutorial: queue is an unattended Smart-Agent tab

Read this if you already know the Koa SmartBatch dashboard and want the Python equivalent.

### The problem

A SmartBatch only moved while Smart-Agent was open. The browser walked each row: call the feature, `PUT` the row, fire `BatchConfiguration.notification.webhookUrl`. Close the tab, the batch froze.

`?type=queue` does that same walk **without the tab**. File batches (N rows) and a 1-row API call use the same loop.

Python does **not** write Mongo. Node already has SmartBatch / rows / `smartbatchrows`. We only added attempt history on the row and three endpoints the worker calls.

### Who owns what

| Job | Owner |
| --- | --- |
| Public API (`GET /v2/co/afiliaciones`) | Python |
| JWT check, credits, SISPRO scrape, SmartBatch documents | Node |
| Claim next row / append attempt / customer webhook | Node |
| “Open tab” loop (claim → SISPRO → record attempt) | Python |

Company A never talks to SmartBatch directly for a single lookup. They hit Python. They can still open Smart-Agent and see the same batch.

### Two `type` values

Same path, same query validation (`documentType`, `documentNumber`, `date`).

| `type` | What happens | Response |
| --- | --- | --- |
| omitted or `sync` | Wait on Node SISPRO, return that body | `200` / `401` / `404` / `409` / `504` |
| `queue` | Create a 1-row SmartBatch. **Do not** call SISPRO on this request. Kick the worker in the background | `202` `{ status, batchId, rowIndex, attemptCount }` |

Middleware: `sispro_middleware.py`. `type` must be `sync` or `queue` (or missing). Controller: `sispro_controller.py` — `if type == "queue": enqueue(...)` else `Module.get(...)`.

```http
GET /v2/co/afiliaciones?documentType=CC&documentNumber=1007463534&date=09/05/2008&type=queue
Authorization: Bearer <same client JWT as Node>
```

```json
{
  "status": "queued",
  "batchId": "66f0…",
  "rowIndex": 0,
  "attemptCount": 0
}
```

Poll Node `GET /v2/smart-batches/:id` or watch Smart-Agent. When the row is terminal, Node POSTs `notification.webhookUrl` if the SISPRO Queue config has one.

### Sequence (queue)

1. **Enqueue** — Python `POST /v2/smart-batches/from-queue` with `{ documentType, documentNumber, date }`. Node finds the client's default config by `{ client, queueKey: "co.sispro.queue" }` (`Queue SISPRO`, one step `colombia_api_affiliations`, `maxRetries` 3). First call creates it; the 2nd / 3rd / 4th reuse that same document (display name can change; the key does not). Then it inserts a 1-row SmartBatch on that `configId`.
2. **202** goes back to Company A immediately.
3. **BackgroundTasks** runs `sispro_queue_worker.process_next(authorization)` after the response (Starlette `BackgroundTasks` ≈ “do this after I reply”, not Redis).
4. **Claim** — `GET /v2/smart-batches/queue/next`. Node marks that row `processing` and returns `{ batchId, rowIndex, inputData, attemptCount, maxRetries }`. Skips batches that already have a FeatureRunner `run` (server-side start).
5. **Execute** — same `sispro_module.get` as sync, JWT from the original request.
6. **Record** — `POST /v2/smart-batches/:id/rows/:rowIndex/attempts`. Node bumps `attemptCount`, pushes `{ attempt, at, status, statusCode, code, message }`, merges `results` on success. Payloads stay on the row / `smartbatchrows`, not on every attempt.
7. **Webhook** — if the row is **terminal** and `batchConfiguration.notification.webhookUrl` is set, Node sends the same payload the tab already sent:
   - `row.completed` — this row is done, others still running
   - `batch.completed` — every row is done  
   Empty URL → skip. Python never POSTs the customer webhook.
8. Loop until `claim_next` returns `null`.

Retryable = 429, 5xx, or codes `Timeout` / `ServiceUnavailable` / `timeout_database` / `upstream_error`. **Not** 404 or `MissingParameter`. A retryable fail stays claimable until `attemptCount >= maxRetries`. Then the row is finished and the webhook can fire.

### Node pieces to keep in your head

```
verifik-backend/Repositories/SmartBatch/
  models/smart-batch.model.js          # rows[].attemptCount, rows[].attempts[]
  modules/smart-batch.module.js        # createFromQueue, claimNext, appendAttempt, notifyRowOrBatch
  routes/smart-batch.routes.js         # /from-queue and /queue/next BEFORE /:id
```

`notifyRowOrBatch` is the old `updateRow` webhook block, extracted. Tab and worker share it.

### Python pieces

```
sispro_controller.get          → sync or enqueue
smart_batch_module             → thin httpx to those three Node routes
sispro_queue_worker            → while claim: SISPRO then append_attempt
sispro_module.get              → strips `type` so Node SISPRO never sees it
```

`BackgroundTasks` is in-process. Restart the process and an in-flight loop dies. Redis / TaskIQ when that is too small. Hour / day / total retry caps are also later — this pass is only per-row `maxRetries`.

### Try it

```bash
# sync — same as before (wait for SISPRO)
curl -sS -H "Authorization: Bearer $JWT" \
  "http://localhost:3062/v2/co/afiliaciones?documentType=CC&documentNumber=1007463534&date=09/05/2008"

# queue — 202, then the worker claims and writes attempts
curl -sS -H "Authorization: Bearer $JWT" \
  "http://localhost:3062/v2/co/afiliaciones?documentType=CC&documentNumber=1007463534&date=09/05/2008&type=queue"
```

Then open Smart-Agent on that `batchId`. List rows show `attempts: N`. Detail shows the timeline.

Swagger (`/docs`) documents `type`. Click **Authorize**, then **Try it out**.

### Tests (no live Node)

`tests/test_sispro.py` mocks httpx. The five Supre production-ok rows are parametrized (`1007463534`, `1064118303`, `1003005729`, `32288038`, `1067592151`). Queue tests assert `202` and that SISPRO is **not** called on the enqueue request. Worker tests assert a `completed` attempt on 200 and a `failed` attempt on 404.

```bash
pytest tests/test_sispro.py
```
