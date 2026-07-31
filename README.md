# Error Analysis — Datadog Checkout / Order Create

Internal tooling to investigate and reproduce **Ingram Micro Order Create** failures
from **Datadog US5** logs. The app covers the full loop:

1. **Search** checkout logs and extract Hermes request/response payloads
2. **Rebuild** a Postman-style Order Create curl (v6 body, or **v2→v6** conversion)
3. **Replay** against UAT/QA with a fresh `customerOrderNumber`, then poll Datadog for SUCCESS/FAILED
4. **Resolve** two-char CORORA error codes via the legacy error-code lookup service

Entry points:

| Entry point | Kind | Description |
|-------------|------|-------------|
| `error-analysis` | CLI (Typer) | Full command surface |
| `error-analysis-api` | FastAPI | HTTP API on port **8010** |
| `web/` | React + Vite | Browser UI on **5173** (dev) or served by the API (prod) |

For module-level detail, see [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Prerequisites

Install these on your machine before cloning:

- **Git**
- **Python 3.10+** (`python` or `python3` on PATH; on Windows the `py` launcher also works)
- **Node.js 18+** and **npm** (for the React UI)
- A code editor with a terminal (VS Code / Cursor)

## Clone from GitHub

In a terminal (or the VS Code / Cursor terminal):

```bash
git clone https://github.com/DeepakBhengra/error-analysis.git
cd error-analysis
```

Open the folder in VS Code:

```bash
code .
```

(Or **File → Open Folder…** and select `error-analysis`.)

If `web/package.json` is missing after clone (older `main`), switch to the setup branch that adds the Vite manifest:

```bash
git fetch origin
git checkout cursor/setup-dev-environment-c154
```

## Setup and run in the VS Code terminal

Open the integrated terminal: **Terminal → New Terminal** (`` Ctrl+` `` / `` Cmd+` ``).
All commands below start from the **repo root** (`error-analysis/`).

### 1. Create a virtual environment and install Python deps

**Windows (PowerShell):**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev,web]"
```

If `python` is not found, try `py -m venv .venv` instead.

**macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,web]"
```

You should see `(.venv)` in the terminal prompt after activation.

### 2. Create `.env` and add credentials

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Edit `.env` in VS Code and set:

**Datadog (required)**

- `DD_API_KEY` — API key from Organization Settings → API Keys
- `DD_APP_KEY` — Application key with `logs_read_data` scope
- `DD_SITE` — `us5.datadoghq.com` (default)

**Order Create replay (required for curl / replay / UI Re-Submit)**

- `ORDER_CREATE_USERNAME` / `ORDER_CREATE_PASSWORD` — Basic Auth for `/resellers/v6/orders`
- `ORDER_CREATE_COOKIE` — optional session cookie
- `DEFAULT_ORDER_CREATE_TARGET` — `uat` or `qa` (default `uat`)
- `DEFAULT_REPLAY_MODE` — `one_up` or `random` (default `one_up`)

**Optional**

- `CHECKOUT_SERVICE` / `ORDER_CREATE_SERVICES` — default
  `AsyncOrderCreate,OrderCreate_v6*,OrderCreate_v2*`
- `ORDER_CURL_API_KEY` — inbound key for `POST /api/v1/order-curl`
- `LOOKUP_API_*` — legacy CORORA error-code lookup service

Credentials are also editable from the web **Settings** tab (`GET`/`PUT /api/settings`).

### 3. Run the application (API + UI)

You need **two** VS Code terminals (click **+** in the terminal panel for a second one).
Activate `.venv` in each Python terminal first.

**Terminal 1 — API (port 8010)**

From the repo root, with `.venv` active:

```bash
error-analysis-api
```

Leave this running. You should see Uvicorn listening on `127.0.0.1:8010`.

**Terminal 2 — Web UI (port 5173)**

```bash
cd web
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Leave this running. Vite prints `Local: http://127.0.0.1:5173/`.

### 4. Open the UI

In your browser (on the **same machine** as the terminals), open:

**http://127.0.0.1:5173**

Vite proxies `/api` to the API on port 8010.

Quick credential check (optional, third terminal, `.venv` active):

```bash
error-analysis validate
```

### Windows one-shot (optional)

With `.venv` already installed and `.env` configured:

```powershell
.\start-dev.ps1
```

This starts the API and then the Vite UI in one PowerShell session.

### Production-style single process (Windows)

```powershell
.\build-prod.ps1
.\start-prod.ps1
```

Or double-click **`Start Error Analysis.bat`**. Then open **http://127.0.0.1:8010**.

### Troubleshooting

| Symptom | Fix |
|---------|-----|
| `python: command not found` | Use `python3` or `py`, or install Python 3.10+ and reopen the terminal |
| `npm error ENOENT … package.json` | You are on a branch without the web manifest — `git checkout cursor/setup-dev-environment-c154` |
| Browser: `ERR_CONNECTION_REFUSED` on `:5173` | Start Vite with `--host 127.0.0.1`; open the URL on the same machine (not a remote PC’s Edge against a VM) |
| API / Datadog errors | Confirm `.env` has real `DD_API_KEY` / `DD_APP_KEY` (not the example placeholders) |
| Order Create POST fails | Connect to the corporate VPN; set `ORDER_CREATE_USERNAME` / `ORDER_CREATE_PASSWORD` |

## Primary usage

Validate credentials:

```bash
error-analysis validate
```

### Fetch request / response payloads

Free-text search (Datadog Logs search bar) — use `--text`.
By default results are limited to `AsyncOrderCreate`, `OrderCreate_v6*`, and
`OrderCreate_v2*` (wildcards match versioned prod services such as `OrderCreate_v6_1`):

```bash
error-analysis fetch-request \
  --text DEEPAKDDTEST1 \
  --from 2026-06-17T00:00:00Z \
  --to 2026-07-15T23:59:59Z \
  --out results/request.json
```

Query shape:

```text
DEEPAKDDTEST1 service:(AsyncOrderCreate OR OrderCreate_v6* OR OrderCreate_v2*)
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

The command searches Datadog and extracts:

- request / `RequestLogPayload` (Hermes Request messages and attributes)
- response / `ResponseLogPayload` (Hermes Response messages and attributes)

Logs with either payload are included in the output.

## Build Order Create curl

From a `fetch-request` JSON file, build a Postman-style Order Create curl:

- **Body/URL** preference:
  1. Prod v6 (`AsyncOrderCreate` / `OrderCreate_v6_*` on `uschileai1401–1404`)
  2. Portal `OrderCreate_v6` / `uschileai2503`
  3. Legacy `OrderCreate_v2` body, **converted to v6** via `convert_v2_to_v6`
- **Headers** from sibling `OrderCreate_v2*` (`IM-CountryCode`, `IM-CustomerNumber`,
  `IM-CorrelationID`, `IM-SenderID`), or from AsyncOrderCreate/v6 metadata
- `Authorization: Basic …` from `ORDER_CREATE_USERNAME` / `ORDER_CREATE_PASSWORD`
- Optional `Cookie` from `ORDER_CREATE_COOKIE`
- `--target uat|qa` selects the Order Create host for AsyncOrderCreate bodies

```bash
error-analysis build-order-curl \
  --from-file results/request.json \
  --target uat \
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
4. POST Order Create (same URL/headers/auth as the curl builder; `--target uat|qa`)
5. Poll Datadog until a response preamble appears (or timeout)
6. Always write `order-create-result.json` with `statuscode`, `responsemessage`, `errorcode`
7. On **FAILED**, also write `order-create-error-report.json`
8. Prefer a two-char CORORA code from OrderCreate_v2 XML when the JSON status is numeric

Primary (search + replay):

```bash
error-analysis replay-order \
  --text DEEPAKDDTEST12 \
  --search-from 2026-06-17T00:00:00Z \
  --search-to 2026-07-15T23:59:59Z \
  --target uat \
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

Optional flags: `--poll-interval 15`, `--timeout 180`, `--from` / `--to` (post-replay poll window), `--env`, `--index`, `--target`.

## v2→v6 pair mining (rule gaps)

Mine real Order Create v2/v6 request pairs linked by JobID, then diff
`convert_v2_to_v6` against the actual v6 payload to find conversion rule gaps:

```bash
error-analysis mine-pairs --count 20 --out-dir results/v2v6-pairs
error-analysis check-pairs --pairs-dir results/v2v6-pairs
error-analysis mine-validation-pairs --count 10 --out-dir results/v2v6-pairs-validation
```

`mine-pairs` defaults to the last 15 days. `mine-validation-pairs` holds out
training POs (or use `--prior-window` for an earlier time range).

## Legacy / debug fetch

```bash
error-analysis fetch --query "\"G0D82\"" --from "2026-07-08T00:00:00Z" --to "2026-07-08T00:15:00Z"
error-analysis fetch --url "https://us5.datadoghq.com/logs?query=..."
```

## Web UI (Order Create Search & Replay)

React UI (COBOL Scanner–style layout) plus FastAPI backend on port **8010**
(avoids clashing with apps on 8000, e.g. COBOL Error Scanner).

For clone, install, and VS Code terminal run steps, see
**[Setup and run in the VS Code terminal](#setup-and-run-in-the-vs-code-terminal)** above.
Vite proxies `/api` → `8010`. Restart `npm run dev` after changing `vite.config.ts`.

### UI flow

- Enter a customer order number, choose **One-up** or **Random**, pick **UAT/QA**, click **RUN**
- **RUN** previews an editable curl via `POST /api/order-request` (no Order Create POST yet;
  banner shows `READY` and source `v6` or `v2-converted`)
- Edit the curl and click **Re-Submit** → `POST /api/resubmit` (bumps/randomizes the order
  number, POSTs, polls Datadog, classifies SUCCESS/FAILED)
- View SUCCESS/FAILED banner, metrics, and results table (Impulse Order Number = `globalorderid`)
- Click a two-char error code → legacy lookup popup; resolve caches business logic under `results/`
- **Settings** tab edits Datadog / Order Create credentials and default target/mode (writes `.env`)

Immediate HTTP validation failures can auto-repair deterministic headers
(`IM-CorrelationId`, `Content-Type`); other fields stay unresolved for manual edit.

The Order Create Curl panel also shows a live **Probably D / Probably S** hint
(scored from prod attribute differences). See
[`docs/observations/order-type-d-vs-s/`](docs/observations/order-type-d-vs-s/).

### API surface

| Method & path | Purpose |
|---------------|---------|
| `GET /api/health` | Validate Datadog credentials |
| `GET` / `PUT /api/settings` | Read/update `.env` settings (secrets masked on GET) |
| `POST /api/order-request` | Search Datadog → editable v6 curl preview |
| `POST /api/run` | Full search → replay → poll → classified result |
| `POST /api/resubmit` | Replay from an edited curl |
| `POST /api/error-lookup` | Proxy to legacy CORORA error-code lookup |
| `POST /api/resolve-error` | Lookup + cache `results/{CODE} Business Logic.json` |
| `POST /api/v1/order-curl` | Authenticated curl generator (see below) |

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

## Tests

```bash
pytest
```
