# verifik-smartcheck

FastAPI service in front of `verifik-backend`. Home and health are the scaffold. SISPRO and cédula are first-class facades. Every other catalog URL from `app-features-final.json` is registered the same way: **sync proxy** by default, **queue** when `?type=queue`.

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
- Cédula (proxies Node): http://localhost:8000/v2/co/cedula
- Other catalog URLs (e.g. Peru): http://localhost:8000/v2/pe/cedula
- Swagger: http://localhost:8000/docs (one operation per catalog feature)

`VERIFIK_API_URL` comes from `.env` (see `app/core/config.py`). Process env wins, then `.env`, then the class default `https://verifik.app`. Pass the same `Authorization: Bearer <jwt>` header Company A already uses on Node. Python does not have a JWT secret.

Queue tick needs the same `VERIFIK_INTERNAL_SECRET` on Python and Node. Leave it empty and the lifespan loop does not start. `QUEUE_TICK_ENABLED=false` in pytest so tests do not tick. After you change `.env`, restart uvicorn — `get_settings()` is cached.

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
    modules/smart_batch_module.py          # generic from-queue + HMAC claim + invoke_claimed
    modules/sispro_queue_worker.py         # tick: HMAC claim → claimed path + attempt
  repositories/cedula/                     # GET /v2/co/cedula (sync + queue)
  repositories/catalog/                    # remaining AppFeature URLs from app_features.json
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

SISPRO query matches Node Joi: `documentType` (`CC|CE|PA|PE`), `documentNumber` (min 5), `date` (`DD/MM/YYYY`), optional `force` / `audit` / `type`. Cédula matches Node: `documentType` (`CC|PPT`), `documentNumber` (5–10), no date, optional `type`. Missing/invalid query is `409` + `MissingParameter`. Node’s own 200/401/404/409 body is returned as-is. Timeout is `504`; Node unreachable is `503`.

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
| Public API (`GET /v2/co/afiliaciones`, `GET /v2/co/cedula`) | Python |
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

1. **Enqueue** — Python `POST /v2/smart-batches/from-queue` with a **feature spec** (`queueKey`, `featureCode`, `name`, `inputData`). Node finds `{ client, queueKey }` or creates that config (`executor: "queue"`). SISPRO is the first caller (`co.sispro.queue`); cédula is the second (`co.cedula.queue` / `colombia_api_identity_lookup`).
2. **202** goes back to Company A immediately. The customer JWT is **not** stored.
3. **Immediate kick** — `BackgroundTasks` runs one `process_next` after the reply (same as the tick).
4. **Tick** — uvicorn lifespan loops every `QUEUE_TICK_SECONDS`. No cron URL. Set `QUEUE_TICK_ENABLED` / `VERIFIK_INTERNAL_SECRET` in `.env`.
5. **Claim** — `GET /v2/internal/smart-batches/queue/next` with `x-verifik-internal-key` = sha256 of the shared secret. Node claims the oldest `executor: "queue"` row and **mints a 300s client JWT** (same as FeatureRunner). Restart-safe: Mongo holds the row; the next tick mints a new token.
6. **Execute** — `GET`/`POST` the **claimed `path`** (from the config's AppFeature) with the minted Bearer so credits still bill that client. Not hardcoded to SISPRO.
7. **Record** — `POST /v2/smart-batches/:id/rows/:rowIndex/attempts` with the minted Bearer. Node fires `notification.webhookUrl` on a terminal row/batch.
8. Loop until claim is empty or `QUEUE_TICK_MAX_ROWS`.

We do **not** put JWTs in Redis or Mongo. Stale `processing` rows older than the mint TTL are claimable again (Python died mid-attempt).

`executor` on the config/batch: `queue` (this worker), `featureRunner` (Node Start), `browser` (tab only). Smart-Agent can set it; Start for `queue` only flips status. The UI polls progress.

Retryable = 429, 5xx, or codes `Timeout` / `ServiceUnavailable` / `timeout_database` / `upstream_error`. **Not** 404 or `MissingParameter`.

### Node pieces to keep in your head

```
verifik-backend/Repositories/SmartBatch/
  models/smart-batch.model.js                 # executor + rows[].attempts[]
  routes/smart-batch-internal.routes.js       # GET /v2/internal/smart-batches/queue/next
  modules/smart-batch.module.js               # claimNext HMAC + mintRunnerToken
```

### Python pieces

```
app/main.py lifespan           → tick loop (no cron URL)
smart_batch_module             → generic from-queue + HMAC claim + invoke_claimed
sispro_queue_worker            → claim HMAC → invoke claimed path + attempt
sispro_module.SISPRO_QUEUE     → first product spec
cedula_module.CEDULA_QUEUE     → second product spec (`co.cedula.queue`)
```

Hour / day / total retry caps and Redis / TaskIQ stay later. This pass is per-row `maxRetries` + the in-process tick.

### Try it

```bash
# sync — same as before (wait for SISPRO)
curl -sS -H "Authorization: Bearer $JWT" \
  "http://localhost:8000/v2/co/afiliaciones?documentType=CC&documentNumber=1007463534&date=09/05/2008"

# queue — 202, then the worker claims and writes attempts
curl -sS -H "Authorization: Bearer $JWT" \
  "http://localhost:8000/v2/co/afiliaciones?documentType=CC&documentNumber=1007463534&date=09/05/2008&type=queue"

# cédula queue — six cached CC numbers share Queue Cedula (co.cedula.queue)
for n in 56097217 63535790 1023942104 34503117 49716272 64585026; do
  curl -sS -H "Authorization: Bearer $JWT" \
    "http://localhost:8000/v2/co/cedula?documentType=CC&documentNumber=$n&type=queue"
done
```

Then open Smart-Agent on that `batchId`. List rows show `attempts: N`. Detail shows the timeline.

Swagger (`/docs`) documents `type`. Click **Authorize**, then **Try it out**.

### Tests (no live Node)

`tests/test_sispro.py` and `tests/test_cedula.py` mock httpx. Pytest sets `QUEUE_TICK_ENABLED=false` so the lifespan loop does not run. Queue tests assert `202` and the product spec (`queueKey` / `featureCode`). Worker tests assert a `completed` attempt on 200, a `failed` attempt on 404, and that SISPRO + attempt use the **minted** Bearer from claim — not the enqueue JWT.

```bash
pytest tests/test_sispro.py tests/test_cedula.py
```
