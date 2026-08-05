# Error Analysis — Datadog Checkout Request Fetcher

Fetch Hermes Order Simulate request JSON from Datadog checkout logs (US5).

## Setup

1. Create a virtual environment and install:

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -e ".[dev]"
```

2. Copy `.env.example` to `.env` and set your Datadog credentials (one of):

- **Access token (preferred):** `DD_ACCESS_TOKEN` — Personal or Service Access Token
  (Organization Settings → Personal / Service Access Tokens; needs logs read scope).
  Sent as `Authorization: Bearer …`.
- **Or classic keys:** `DD_API_KEY` + `DD_APP_KEY` (App key needs `logs_read_data`)
- `DD_SITE` — `us5.datadoghq.com` (default)

## Primary usage

Validate credentials:

```bash
error-analysis validate
```

Free-text search (Datadog Logs search bar) — use `--text`.
By default results are limited to `OrderCreate_v6` and `OrderCreate_v2`:

```bash
error-analysis fetch-request \
  --text DEEPAKDDTEST1 \
  --from 2026-06-17T00:00:00Z \
  --to 2026-07-15T23:59:59Z \
  --out results/request.json
```

Query shape:

```text
DEEPAKDDTEST1 service:(OrderCreate_v6 OR OrderCreate_v2)
```

Search by explicit identifiers:

```bash
error-analysis fetch-request \
  --correlation-id G0D82 \
  --job-id JOB-123 \
  --customer-po PO-98765 \
  --from 2026-07-08T00:00:00Z \
  --to 2026-07-08T23:59:59Z \
  --env uat \
  --out results/request.json
```

Required:
- `--from` / `--to` — time window
- at least one of `--text`, `--correlation-id`, `--job-id`, `--customer-po`

Optional:
- `--env` — environment filter
- `--service` — override service filter (comma-separated)
- `--no-service-filter` — plain search-bar style (no `service:` clause)

`--text` is free-text only. Output stores it as `search_text`; `correlation_id` stays null unless `--correlation-id` is passed.
Default services: `OrderCreate_v6`, `OrderCreate_v2`.

The command searches Datadog and extracts:
- request / `RequestLogPayload` (Hermes Request messages and attributes)
- response / `ResponseLogPayload` (Hermes Response messages and attributes)

Logs with either payload are included in the output.

## Build Order Create curl

From a `fetch-request` JSON file, build a Postman-style Order Create curl:

- Body/URL from portal `OrderCreate_v6` / `uschileai2503` (`resellerInfo` + `lines`)
  when present (body = full Datadog `request`)
- Headers from `OrderCreate_v2` / `uschileai2501`:
  `IM-CountryCode`, `IM-CustomerNumber`, `IM-CorrelationID`, `IM-SenderID`
- `Authorization: Basic …` from `ORDER_CREATE_USERNAME` / `ORDER_CREATE_PASSWORD`
- Optional `Cookie` from `ORDER_CREATE_COOKIE`

```bash
error-analysis build-order-curl \
  --from-file results/request.json \
  --out results/order-create-body.json
```

Requires `ORDER_CREATE_USERNAME` / `ORDER_CREATE_PASSWORD` in `.env` (Basic Auth).
Generated curls include a real `Authorization: Basic …` token by default.
Pass `--redact-password` when sharing curls in tickets/chat.
Use `--index N` to pick among multiple matches.

## Replay Order Create + check ResponseLogPayload

One command: search a customer order number → build Order Create → re-run with
a fresh `customerOrderNumber` → store SUCCESS/FAILED result.

1. Fetch Order Create logs for `--text` (or load `--from-file`)
2. Default replay order number = trailing digit **+1** (`DEEPAKDDTEST12` → `DEEPAKDDTEST13`)
3. Or pass `--order-number …` / `--random`
4. POST Order Create (same URL/headers/auth as the curl builder)
5. Poll Datadog until a response preamble appears (or timeout)
6. Always write `order-create-result.json` with `statuscode`, `responsemessage`, `errorcode`
7. On **FAILED**, also write `order-create-error-report.json`

Primary (search + replay):

```bash
error-analysis replay-order \
  --text DEEPAKDDTEST12 \
  --search-from 2026-06-17T00:00:00Z \
  --search-to 2026-07-15T23:59:59Z \
  --out-dir results
```

From an existing fetch file:

```bash
error-analysis replay-order \
  --from-file results/request-DEEPAKDDTEST12.json \
  --out-dir results
```

Provide exactly one of `--text` or `--from-file`. With `--text`, `--search-from` / `--search-to` are required.

Artifacts under `--out-dir` (default `results/`):

- `order-create-source-logs.json` — source Datadog records (when using `--text`)
- `order-create-replay-body.json` — body actually POSTed
- `order-create-replay.curl.txt` — equivalent curl for the replay
- `order-create-replay-logs.json` — Datadog records for the new order number
- `order-create-result.json` — SUCCESS/FAILED/TIMEOUT summary (`statuscode`, `responsemessage`, `errorcode`)
- `order-create-replay-summary.json` — same payload as the result file
- `order-create-error-report.json` — written when `responsestatus` is FAILED

Exit codes: `0` SUCCESS, `1` FAILED/UNKNOWN, `2` timeout waiting for logs.

Optional flags: `--poll-interval 15`, `--timeout 180`, `--from` / `--to` (post-replay poll window), `--env`, `--index`.

## Legacy / debug fetch

```bash
error-analysis fetch --query "\"G0D82\"" --from "2026-07-08T00:00:00Z" --to "2026-07-08T00:15:00Z"
error-analysis fetch --url "https://us5.datadoghq.com/logs?query=..."
```

## Web UI (Order Create Search & Replay)

React UI (COBOL Scanner–style layout) plus FastAPI backend that wraps
`replay-order` (Datadog search → Order Create replay → SUCCESS/FAILED).

1. Install API deps (from the project root, with venv active):

```bash
pip install -e ".[web]"
```

2. Start the API on **port 8010** (uses `.env` for Datadog + Order Create credentials).
   Port 8010 avoids clashing with other local apps on 8000 (e.g. COBOL Error Scanner):

```bash
error-analysis-api
```

**Windows (API + UI in one step — development):**

```powershell
.\start-dev.ps1
```

Or:

```bash
uvicorn error_analysis.api:app --reload --host 127.0.0.1 --port 8010
```

3. In another terminal, start the UI:

```bash
cd web
npm install
npm run dev
```

Open http://127.0.0.1:5173 — Vite proxies `/api` to the Order Replay API on port 8010.
Restart `npm run dev` after changing `vite.config.ts` so the proxy target updates.

### Authenticated Order Curl API

Generate a full Order Create curl from a customer order number only.
Requires `ORDER_CURL_API_KEY` in `.env` and the same Datadog + Order Create credentials used by the UI.

```bash
curl --location "http://127.0.0.1:8010/api/v1/order-curl" \
  --header "X-API-Key: your_order_curl_api_key" \
  --header "Content-Type: application/json" \
  --data-raw "{\"customerOrderNumber\": \"DEEPAKDDTEST8\"}"
```

Request body:

```json
{"customerOrderNumber": "DEEPAKDDTEST8"}
```

Successful response:

```text
curl --location 'https://.../resellers/v6/orders' \
--header 'IM-CountryCode: US' \
--header 'Authorization: Basic ...' \
--data-raw '{ ... }'
```

The response is `text/plain` and contains the complete curl shown in the UI,
including generated headers and the full JSON body. The endpoint searches the
default 30-day Datadog window and uses `DEFAULT_ORDER_CREATE_TARGET` (`uat`/`qa`).
Set it to `qa` to generate the QA URL. Missing or invalid `X-API-Key` returns `401`.

### One-click production app (Windows)

Build the UI once, then launch API + UI from a single process on port **8010**:

```powershell
.\build-prod.ps1
```

Double-click **`Start Error Analysis.bat`** (or run `.\start-prod.ps1`).  
Opens http://127.0.0.1:8010 — leave the console window open; Ctrl+C to stop.

Requires `.venv` with `pip install -e ".[web]"`, Node.js for the build step, and a configured `.env`.

UI flow:

- Enter a customer order number, choose One-up or Random, click **RUN**
- View SUCCESS/FAILED banner, metrics, and results table (Impulse Order Number = `globalorderid`)
- Edit the generated curl and click **Re-Submit** to replay again

The Order Create Curl panel also shows a live **Probably D / Probably S** hint
(scored from prod attribute differences). See
[`docs/observations/order-type-d-vs-s/`](docs/observations/order-type-d-vs-s/).

## Application logs

Runtime errors and API failures are written under ``logs/``:

- ``logs/error-analysis.log`` — general application log
- ``logs/error-analysis-errors.log`` — warnings and errors only

Configure with:

- ``ERROR_ANALYSIS_LOG_LEVEL`` — ``DEBUG``, ``INFO``, ``WARNING``, or ``ERROR`` (default ``INFO``)
- ``ERROR_ANALYSIS_LOG_DIR`` — directory for log files (default ``logs/``)

CLI also accepts ``--log-level``.

## Tests

```bash
pytest
```
