# Error Analysis — Architecture Document

> **Application:** Datadog Checkout / Order Create Request Fetcher, Replayer & Error Resolver
> **Package:** `error-analysis` (v0.1.0)
> **Runtime:** Python ≥ 3.10 (backend/CLI) + React 19 / Vite (web UI)
> **Datadog site:** US5 (`us5.datadoghq.com`) by default

---

## 1. Purpose & Overview

Error Analysis is an internal tooling application for investigating and reproducing
**Ingram Micro Order Create** failures using **Datadog logs**. It automates the full
loop an engineer would otherwise do by hand:

1. **Search Datadog** checkout logs for a customer order (by free-text, correlation ID,
   job ID, or customer PO) and extract the **Hermes Order Simulate** request/response
   JSON (`RequestLogPayload` / `ResponseLogPayload`).
2. **Rebuild an Order Create request** (Postman-style `curl`) from those logs — either
   directly from a v6 portal body, or by **converting a legacy OrderCreate_v2 payload
   into a v6 body** and attaching the correct `IM-*` headers and Basic Auth.
3. **Replay** the order against the UAT/QA Order Create endpoint with a fresh
   `customerOrderNumber` (bump +1 or random), then **poll Datadog** until the response
   preamble appears and classify the outcome **SUCCESS / FAILED / TIMEOUT / UNKNOWN**.
4. **Resolve error codes** on failure by mapping two-char CORORA codes (e.g. `D9`, `EN`)
   to business-logic explanations through an external legacy error-code lookup service.
5. A secondary **v2→v6 rule-mining** pipeline mines real v2/v6 request pairs from
   Datadog and diffs the converter output against actual v6 payloads to find conversion
   rule gaps.

The application ships three entry points:

| Entry point | Kind | Description |
|-------------|------|-------------|
| `error-analysis` | CLI (Typer) | Full command surface (validate, fetch, replay, mine, etc.) |
| `error-analysis-api` | FastAPI (uvicorn) | HTTP API on port **8010** wrapping the search→build→replay flow |
| `web/` | React + Vite SPA | Browser UI (port **5173**) that proxies `/api` to the FastAPI backend |

---

## 2. High-Level Architecture

```
                          ┌─────────────────────────────────────────────┐
                          │                 React SPA (web/)             │
                          │  App.tsx · SearchBar · CurlEditor · Results  │
                          │  ErrorCodeModal · StatusBanner · MetricCards │
                          └───────────────────────┬─────────────────────┘
                                                   │ /api/* (Vite proxy :5173 → :8010)
                                                   ▼
                          ┌─────────────────────────────────────────────┐
                          │            FastAPI backend (api.py)          │
                          │  /order-request /run /resubmit /error-lookup │
                          │  /resolve-error /health                      │
                          └───────────────────────┬─────────────────────┘
                                                   │  (shared service layer)
    CLI (cli.py, Typer) ───────────────────────────┤
                                                   ▼
   ┌───────────────────────────────────────────────────────────────────────────┐
   │                            Core service layer (src/error_analysis)          │
   │                                                                             │
   │   datadog/           extractors/          order_create/        error_lookup/│
   │   ─ client           ─ hermes_request      ─ curl_builder        ─ client   │
   │   ─ search           ─ request_log_payload ─ curl_parser         ─ resolve  │
   │   ─ query_builder    ─ order_create_v2_    ─ v2_to_v6                        │
   │   ─ fetch_request       response           ─ order_number                   │
   │   ─ url_parser                             ─ replay                          │
   │   ─ models/errors                          ─ response_check                 │
   │                                            ─ pair_mining                    │
   └───────────┬───────────────────────────────────────┬───────────────┬────────┘
               │                                        │               │
               ▼                                        ▼               ▼
      ┌──────────────────┐              ┌────────────────────────┐  ┌──────────────────┐
      │  Datadog Logs API│              │ Order Create endpoint  │  │ Legacy Error-Code│
      │  api.v2/logs/... │              │ imservices-uat/qa ...  │  │ Lookup service   │
      │  api.v1/validate │              │ /resellers/v6/orders   │  │ (COBOL mapper)   │
      └──────────────────┘              └────────────────────────┘  └──────────────────┘
```

**External dependencies (all HTTP):**
- **Datadog Logs API** — `https://api.us5.datadoghq.com/` (v2 log search, v1 credential validate).
- **Order Create v6 endpoint** — `imservices-{uat|qa}-usch01.corporate.ingrammicro.com:9043/resellers/v6/orders` (requires corporate VPN).
- **Legacy Error-Code Lookup service** — COBOL error mapper (default `http://127.0.0.1:8000/api/v1/lookup`).

---

## 3. Technology Stack

### Backend / CLI (Python)
| Concern | Library |
|---------|---------|
| HTTP client | `httpx` (sync client, retries) |
| Data validation / models | `pydantic` v2 |
| Config / secrets | `pydantic-settings` + `python-dotenv` (`.env`) |
| CLI framework | `typer` |
| Web API | `fastapi` + `uvicorn[standard]` (optional `[web]` extra) |
| Testing | `pytest`, `pytest-httpx` (optional `[dev]` extra) |
| Build backend | `hatchling` (src-layout, package `error_analysis`) |

### Frontend (web/)
| Concern | Library |
|---------|---------|
| Framework | React 19 |
| Build / dev server | Vite 8 (`@vitejs/plugin-react`) |
| Language | TypeScript ~6 |
| Linting | oxlint |
| State | React hooks (no external state library) |
| Styling | hand-written CSS (`index.css`, COBOL-Scanner-style layout) |

---

## 4. Repository Layout

```
Error_analsysis/
├── pyproject.toml            # package metadata, deps, entry points, pytest config
├── README.md                 # usage & setup
├── start-dev.ps1             # Windows helper: start API (:8010) + Vite UI together
├── .env / .env.example       # Datadog + Order Create + lookup credentials/config
├── results/                  # generated artifacts (fetch JSON, replay results, error reports)
├── src/error_analysis/       # Python package (src-layout)
│   ├── cli.py                # Typer CLI (all commands)
│   ├── api.py                # FastAPI app + endpoints
│   ├── config.py             # Settings (pydantic-settings)
│   ├── __main__.py           # `python -m error_analysis`
│   ├── datadog/              # Datadog API access + query building + extraction glue
│   │   ├── client.py         # HTTP client with retry/backoff & error mapping
│   │   ├── search.py         # cursor-paginated log search generator
│   │   ├── query_builder.py  # build Datadog query strings (service/host/env filters)
│   │   ├── fetch_request.py  # orchestrates search + payload extraction → records
│   │   ├── url_parser.py     # parse a Datadog Logs Explorer URL into params
│   │   ├── models.py         # LogSearchFilter / LogSearchParams / ParsedDatadogUrl
│   │   └── errors.py         # Datadog exception hierarchy
│   ├── extractors/           # parse Hermes / OrderCreate payloads out of log events
│   │   ├── hermes_request.py            # request & response payload extraction
│   │   ├── request_log_payload.py       # RequestLogPayload + JobID/CorrelationID
│   │   └── order_create_v2_response.py  # parse OrderCreate_v2_0 XML responses
│   ├── order_create/         # build/replay/convert Order Create requests
│   │   ├── curl_builder.py   # records → Order Create curl (URL/headers/body)
│   │   ├── curl_parser.py    # parse an edited curl back into URL/headers/body
│   │   ├── v2_to_v6.py       # convert legacy v2 request body → v6 body
│   │   ├── order_number.py   # bump / randomize customerOrderNumber
│   │   ├── replay.py         # POST Order Create + poll Datadog + classify outcome
│   │   ├── response_check.py # classify SUCCESS/FAILED, build result/error reports
│   │   └── pair_mining.py    # mine v2/v6 pairs & diff converter (rule-gap report)
│   └── error_lookup/         # external CORORA error-code → business logic lookup
│       ├── client.py         # POST to legacy lookup API, normalize findings
│       └── resolve.py        # cache result to results/{CODE} Business Logic.json
├── tests/                    # pytest suite + JSON fixtures
└── web/                      # React + Vite SPA
    ├── vite.config.ts        # dev server :5173, proxy /api → :8010
    ├── src/
    │   ├── App.tsx           # top-level page + state machine
    │   ├── api.ts            # fetch wrappers for the FastAPI endpoints
    │   ├── types.ts          # shared TypeScript response/domain types
    │   └── components/       # SearchBar, CurlEditor, ResultsTable, ErrorCodeModal, ...
    └── dist/                 # production build output
```

---

## 5. Configuration & Secrets (`config.py`)

All runtime configuration comes from environment variables (loaded from `.env` via
`pydantic-settings`). `Settings` is the single source of truth:

| Setting (env var) | Purpose |
|-------------------|---------|
| `DD_API_KEY`, `DD_APP_KEY` | Datadog auth (App key needs `logs_read_data`) |
| `DD_SITE` | Datadog site → derives `api_base_url` (`https://api.{site}/`) |
| `DEFAULT_QUERY`, `DEFAULT_STORAGE_TIER`, `DEFAULT_SORT`, `DEFAULT_PAGE_LIMIT` | search defaults |
| `CHECKOUT_SERVICE` / `ORDER_CREATE_SERVICES` | default service filter (`AsyncOrderCreate,OrderCreate_v6*,OrderCreate_v2*`) |
| `ASYNC_ORDER_HOSTS` | prod Order Create hosts (reference/host filter) |
| `ORDER_CREATE_USERNAME` / `_PASSWORD` / `_COOKIE` | Basic Auth + optional cookie for replay |
| `LOOKUP_API_URL`, `LOOKUP_API_KEY`, `LOOKUP_APPLICATION_KEY` | error-code lookup service |
| `LOOKUP_SOURCE_ROOT`, `LOOKUP_RULES_PATH`, `LOOKUP_CORORA_MAPPINGS` | paths passed to the lookup service |

Helper properties: `default_services` (parsed list), `default_async_order_hosts`,
and `api_base_url` (normalizes `DD_SITE` into the Datadog API base URL).

---

## 6. Core Modules (Backend)

### 6.1 Datadog layer (`datadog/`)

- **`client.py` — `DatadogClient`**: thin `httpx.Client` wrapper. Sets `DD-API-KEY` /
  `DD-APPLICATION-KEY` headers, 60s timeout. Implements retry with exponential backoff
  for retryable statuses `{429, 500, 502, 503, 504}` (max 3 retries, honors `Retry-After`),
  maps `401/403` → `DatadogAuthError`, other 4xx/5xx → `DatadogSearchError`, and network
  errors → `DatadogError` (with a DNS/VPN hint). Exposes `validate_credentials()` and
  `search_logs(body)`. Usable as a context manager.
- **`search.py` — `search_logs(client, params)`**: generator that transparently follows
  Datadog's `meta.page.after` cursor, yielding every log event across all pages.
- **`query_builder.py` — `build_checkout_query(...)`**: assembles a Datadog query string
  from free-text/correlation-id/job-id/customer-po terms plus `service:(...)`, `host:(...)`,
  and `env:` filters. Free-text values with whitespace are auto-quoted. Default service
  filter is `AsyncOrderCreate OR OrderCreate_v6* OR OrderCreate_v2*`.
- **`fetch_request.py` — `fetch_request_records(...)`**: the main orchestrator. Builds the
  query, paginates the search, runs `extract_log_payloads` on each event, and returns a
  `FetchRequestResult` dataclass (records + counters: total logs, missing-payload,
  request/response counts). `resolve_service_filter(...)` chooses the service filter
  (override / default / none).
- **`models.py`**: pydantic models `LogSearchFilter`, `LogSearchParams` (serialize to the
  Datadog v2 search body incl. cursor), `ParsedDatadogUrl`, plus `ms_to_iso()` helper.
- **`url_parser.py`**: parses a pasted Datadog Logs Explorer URL (`query`, `from_ts`/`to_ts`
  or `from`/`to`, `storage`, `stream_sort`, `cols`) into a `ParsedDatadogUrl`.
- **`errors.py`**: `DatadogError` base + `DatadogAuthError`, `DatadogRateLimitError`,
  `DatadogSearchError`.

### 6.2 Extractors (`extractors/`)

Log payloads arrive in many shapes (nested attributes, JSON in `message`, XML/TIBCO
wrappers). Extractors normalize them:

- **`hermes_request.py`**: `extract_hermes_request` / `extract_hermes_response` locate the
  Hermes Order Simulate request/response by attribute keys (`RequestLogPayload`,
  `ResponseLogPayload`, `servicerequest`, ...) or by stripping known message prefixes
  (`"Error in Hermes Order Simulate: Request :"` etc.) and parsing embedded JSON. Guards
  against misclassifying a response as a request. `extract_log_payloads` returns the
  `(request, response)` tuple; `build_fetch_request_record` shapes the normalized record
  (`log_id`, `timestamp`, `host`, `service`, `env`, identifiers, `request`/`response`,
  and mirrored `RequestLogPayload`/`ResponseLogPayload`).
- **`request_log_payload.py`**: robust `RequestLogPayload` extraction, including a
  brace-matching scanner that pulls a JSON object embedded inside XML-wrapped messages.
  Also extracts `JobID` and `CorrelationID` (prefix-tolerant XML tags like `<pfx5:JobID>`
  or attribute keys). Used by legacy `fetch` and by pair mining.
- **`order_create_v2_response.py`**: parses **OrderCreate_v2_0 XML** "OrderCreate Response"
  fragments. Handles classic tags (`requestStatus`/`returnCode`/`returnMessage`) and
  preamble-style tags (`responsestatus`/`statuscode`/`responsemessage`), including
  namespace prefixes (e.g. `tns:statuscode`). Prefers a FAILED `responsepreamble` block
  over a warning-level SUCCESS fragment, and clubs `orderBranchNumber-orderNumber` into an
  Impulse Order Number. Key for recovering **two-char CORORA codes** (e.g. `D9`) that the
  JSON response only exposes as a numeric HTTP status.

### 6.3 Order Create layer (`order_create/`)

- **`curl_builder.py`** — the heart of request reconstruction:
  - Classifies records: prod v6 body (AsyncOrderCreate / `OrderCreate_v6_*` on
    `uschileai1401–1404`), portal `OrderCreate_v6`/`uschileai2503`, mapped `OrderCreate_v2`,
    or prod `OrderCreate_v2*`.
  - Picks the **body** from the best available record (prod v6 preferred), and the
    **headers** (`IM-CountryCode`, `IM-CustomerNumber`, `IM-CorrelationID`, `IM-SenderID`)
    from a sibling `OrderCreate_v2` requestpreamble/extendedspecs, or from
    AsyncOrderCreate/v6 metadata (`countryCode`/`customerNumber`).
  - Resolves the target URL via `(service, host)` map or the UAT/QA `target` selector.
  - When the body is a legacy v2 payload, converts it via `convert_v2_to_v6` and marks the
    result `source = "v2-converted"` (else `"v6"`).
  - Emits a **Postman-style curl** (`--location` / `--header` / `--data-raw`) with a real
    or redacted `Authorization: Basic …`. Returns an `OrderCreateCurl` dataclass.
- **`curl_parser.py` — `parse_order_create_curl`**: reverse of the formatter. Parses an
  (edited) curl back into `url` / `headers` / JSON `body` / `authorization`, tolerating
  Postman line continuations and multi-line `--data-raw`.
- **`v2_to_v6.py` — `convert_v2_to_v6`**: converts a legacy Order Create v2 request body
  into a reseller v6 body. Two learned shapes: **simple portal** (sparse lines + small
  allow-list) vs **rich quote/ERP** (`basketid`/`billtosuffix`/header `vmf` → full field
  mapping incl. `shipToInfo`, `vmf`, `shipmentDetails`, credit-card mapping, header
  extendedspecs routing/dropping). Raises `OrderCreateV2ToV6Error` on unconvertible input.
- **`order_number.py`**: `bump_trailing_number` (increment trailing digits, width-preserving),
  `random_order_number` (alpha prefix + UTC timestamp + random suffix), `apply_order_number`
  (deep-copy body and set `customerOrderNumber`/`endCustomerOrderNumber`), and
  `resolve_replay_order_number` (explicit / random / bump+1 selection).
- **`replay.py`** — the replay orchestrator:
  - `run_replay(records, ...)`: build curl → derive new order number → apply to body →
    rebuild curl → `_complete_replay`.
  - `run_replay_from_curl(curl, ...)`: parse an edited curl → new order number → replay,
    preferring `.env` Basic Auth but falling back to the curl's `Authorization`.
  - `_complete_replay`: `post_order_create` (httpx POST, VPN/DNS error hints), then
    `poll_response_logs` on Datadog until a `responsepreamble` appears (with a short grace
    window to let the v2 XML two-char code index), then `find_response_check` and build the
    SUCCESS / FAILED / TIMEOUT / UNKNOWN summary. Writes artifacts to `out_dir` when set.
  - Time-window helpers: `default_time_window` (now-15m … now+5m poll), `default_search_window`.
- **`response_check.py`**: classification + reporting.
  - `find_response_check`: prefers JSON `responsepreamble`; also accepts v2 XML responses.
    Preference: FAILED-with-two-char-code → any FAILED → SUCCESS → first.
  - `classify_preamble` (SUCCESS requires `responsestatus=SUCCESS`, `statuscode=200`,
    `responsemessage=SUCCESS`, no errorcode) and `classify_v2_request_status`.
  - `find_two_char_statuscode_in_sources` / `map_two_char_from_v2_sources`: recover the
    CORORA two-char code from v2 XML when the JSON code is numeric.
  - `build_result_payload` / `build_error_report` / `build_success_summary`: canonical
    result dicts persisted as `order-create-result.json` (and `-error-report.json`).
- **`pair_mining.py`**: research pipeline. Searches `OrderCreate_v6`/`uschileai2503` for
  request payloads + `JobID`, finds the sibling `OrderCreate_v2` request per JobID, persists
  pairs, runs `convert_v2_to_v6`, and diffs against the actual v6 payload (ignoring
  master-data enrichment paths that can't be reconstructed) to produce an aggregated
  **rule-gap report**. Training/validation windows support holdout evaluation.

### 6.4 Error lookup (`error_lookup/`)

- **`client.py`**: `is_two_char_error_code` (CORORA codes = letter + letter/digit, so `400`
  never qualifies). `lookup_error_code(code)` and `lookup_error_field(field)` POST to the
  external lookup service (with `X-API-Key` / `X-Application-Key` + configured source paths),
  and normalize the `findings` response (error_code, historical_resolution, program,
  paragraph, summary, ...). Errors → `ErrorLookupError`.
- **`resolve.py`**: `resolve_error_code` returns a cached `results/{CODE} Business Logic.json`
  if present, otherwise looks it up and persists it. Returns `{cached, path, result}`.

---

## 7. Command-Line Interface (`cli.py`)

Typer app `error-analysis`. Configuration errors surface a friendly "copy `.env.example`"
message. Commands:

| Command | Purpose |
|---------|---------|
| `validate` | Validate Datadog credentials (`api/v1/validate`). |
| `fetch` | Legacy/debug: search by `--query` or Datadog `--url` and extract `RequestLogPayload`. |
| `fetch-request` | Search by `--text` / `--correlation-id` / `--job-id` / `--customer-po` over a `--from`/`--to` window; extract Hermes request + response; write JSON records. |
| `build-order-curl` | From a fetch JSON file, build an Order Create curl (`--target uat/qa`, `--index`, `--redact-password`). Requires `ORDER_CREATE_USERNAME/PASSWORD`. |
| `replay-order` | Search (`--text` + `--search-from/--search-to`) or load (`--from-file`), replay with a new order number (bump+1 default / `--order-number` / `--random`), poll, and write result artifacts. Exit codes: 0 SUCCESS, 1 FAILED/UNKNOWN, 2 TIMEOUT. |
| `mine-pairs` | Mine `count` distinct v2/v6 request pairs linked by JobID into `--out-dir`. |
| `check-pairs` | Diff `convert_v2_to_v6` against actual v6 for mined pairs; emit rule-gap report. |
| `mine-validation-pairs` | Mine holdout/prior-window validation pairs (excludes training POs). |

### `replay-order` artifacts (under `--out-dir`, default `results/`)
`order-create-source-logs.json`, `order-create-replay-body.json`,
`order-create-replay.curl.txt`, `order-create-replay-logs.json`,
`order-create-result.json`, `order-create-replay-summary.json`, and (on FAILED)
`order-create-error-report.json`.

---

## 8. HTTP API (`api.py`)

FastAPI app `Error Analysis Order Replay` (v0.1.0), CORS open (`*`), served by uvicorn on
`127.0.0.1:8010` (chosen to avoid clashing with the COBOL Error Scanner on :8000).

| Method & path | Request model | Behavior |
|---------------|---------------|----------|
| `GET /api/health` | – | Validates Datadog credentials; returns `{ok, datadog}`. |
| `POST /api/order-request` | `OrderRequestPreview` (`text`, `from`/`to`, `index`, `env`, `target`) | Search Datadog and return an **editable v6 curl** (no POST). Reports source `v6` vs `v2-converted`. |
| `POST /api/run` | `RunRequest` (`text`, window, `mode`, `target`, `poll_interval`, `timeout`) | Full search → replay → poll → classified result. |
| `POST /api/resubmit` | `ResubmitRequest` (`curl`, `mode`) | Replay from an **edited curl** (bump/random order number), poll, classify. |
| `POST /api/error-lookup` | `ErrorLookupRequest` (`error_code`) | Proxy to legacy error-code lookup. |
| `POST /api/resolve-error` | `ErrorLookupRequest` | Lookup + cache to `results/{CODE} Business Logic.json`. |

Response shaping (`_api_response`): normalizes outcome/statuscode/responsemessage/
globalorderid/customerOrderNumber, and for FAILED runs **enriches the statuscode**
(`_enrich_failed_statuscode`): prefer a two-char v2 XML statuscode, else map the
`responsemessage` via the error-field lookup — always degrading gracefully so a replay
result is still returned. `_banner_message` builds the user-facing SUCCESS/FAILED banner
text (including Impulse Order Number = `globalorderid`).

HTTP error mapping: config errors → 500, validation/`ValueError` → 400, Datadog failures →
502, no records → 404.

---

## 9. Web UI (`web/`)

React 19 + Vite SPA in a COBOL-Scanner–style layout. Vite dev server runs on **:5173** and
proxies `/api` to **:8010** (`vite.config.ts`). No routing/state libraries — a single
`App.tsx` holds all state via hooks.

**Component tree** (`App.tsx`):
- `AppShell` → `Breadcrumbs`, `MetricCards` (runs / success / failed / latest Impulse),
  `ResultTabs` (all/success/failed filter), `SearchBar` (query + time window + One-up/Random
  mode + UAT/QA target + Run/Cancel/Refresh), `StatusBanner`, `ResultsTable`,
  `ErrorCodeModal`, `CurlEditor`.

**Data flow (`api.ts`):**
- **RUN** → `POST /api/order-request` → returns an editable curl + banner (`READY`,
  `v6` or `v2-converted`).
- **Re-Submit** (from `CurlEditor`) → `POST /api/resubmit` → prepends the new
  `SessionResult` row and updates banner/curl.
- Clicking an error code → `POST /api/error-lookup`; "resolve" on a row →
  `POST /api/resolve-error` (cached business logic). Results render in `ErrorCodeModal`.
- Requests are cancelable via `AbortController`; abort errors are handled distinctly.
- Times are converted to ISO-Z (`toIsoZ`), default search window is the last 30 days.

Shared types (`types.ts`): `Outcome` (`SUCCESS|FAILED|TIMEOUT|UNKNOWN|READY`), `ReplayMode`,
`OrderCreateTarget`, `ReplayApiResponse`, `OrderRequestPreviewResponse`, `SessionResult`,
`ErrorLookupResponse`, etc.

---

## 10. End-to-End Flow (Search → Replay → Resolve)

```
User (UI or CLI)
   │  text / correlation-id / job-id / customer-po + time window
   ▼
build_checkout_query ──► DatadogClient.search_logs (cursor paginated)
   ▼
extract_log_payloads (Hermes request/response, v2 XML) ──► FetchRequestResult.records
   ▼
find_order_create_records ──► build_order_create_curl_from_records
   │        (v6 body directly, or convert_v2_to_v6 for legacy payloads)
   │        + IM-* headers from sibling v2 / async metadata + Basic Auth
   ▼
resolve_replay_order_number (bump+1 / random / explicit) ──► apply_order_number
   ▼
post_order_create (HTTP POST → /resellers/v6/orders, UAT/QA)   [requires VPN]
   ▼
poll_response_logs (Datadog until responsepreamble, w/ grace window)
   ▼
find_response_check ──► classify SUCCESS / FAILED / TIMEOUT / UNKNOWN
   │                     (recover two-char CORORA code from v2 XML if needed)
   ▼
build_result_payload / build_error_report  ──► results/*.json + API/CLI response
   │
   └─(on FAILED, two-char code)─► error_lookup → business-logic resolution (cached)
```

---

## 11. Error Handling & Resilience

- **Datadog**: retry/backoff on transient statuses; explicit auth-error and DNS/VPN hints;
  typed exception hierarchy propagated to CLI (colored messages, exit codes) and API
  (HTTP status mapping).
- **Order Create POST**: `ConnectError`/`RequestError` → actionable `OrderCreateCurlError`
  ("connect to the corporate VPN and retry").
- **Polling**: bounded by `timeout`; a **grace window** covers the lag between the JSON
  response log and the v2 XML log carrying the two-char code.
- **Error lookup**: failures are swallowed during FAILED enrichment so a replay result is
  always returned.
- **Frontend**: `ApiError` carries HTTP status; a bare `502` is rewritten to "API server
  unreachable — start `error-analysis-api`"; requests are cancelable.

---

## 12. Testing

`pytest` suite under `tests/` (configured via `pyproject.toml` with `pythonpath = ["src"]`)
plus JSON fixtures under `tests/fixtures/` (sample Hermes/v2 log events, search pages).
Coverage spans the client, query builder, URL parser, search pagination, extractors
(Hermes + v2 response), curl builder/parser, v2→v6 conversion, order replay, pair mining,
and the FastAPI order-request endpoint (`pytest-httpx` mocks outbound HTTP). Run with
`pytest`.

---

## 13. Running Locally

```bash
# 1. Install (backend + web extra)
python -m venv .venv && .venv\Scripts\activate
pip install -e ".[dev,web]"

# 2. Configure credentials
copy .env.example .env   # set DD_API_KEY / DD_APP_KEY / ORDER_CREATE_* / LOOKUP_*

# 3a. CLI
error-analysis validate
error-analysis replay-order --text DEEPAKDDTEST12 \
  --search-from 2026-06-17T00:00:00Z --search-to 2026-07-15T23:59:59Z --out-dir results

# 3b. API + UI (Windows one-shot)
.\start-dev.ps1            # API :8010 + Vite UI :5173
# or manually:
error-analysis-api        # API on :8010
cd web && npm install && npm run dev   # UI on :5173 (proxies /api → :8010)
```

---

## 14. Key Design Notes

- **Src-layout package** (`src/error_analysis`) with a clean separation: Datadog access,
  payload extraction, Order Create construction/replay, and error lookup are independent
  layers reused by both the CLI and the API (no logic duplicated in `api.py`/`cli.py`).
- **Shape-based detection**: Order Create records are classified by payload shape and
  service/host (not just names), so versioned prod services (`OrderCreate_v6_1`,
  `OrderCreate_v2_0`) and AsyncOrderCreate all work.
- **CORORA two-char code recovery** is a recurring theme: numeric HTTP statuses are mapped
  back to the meaningful two-char business code via the v2 XML response and/or the error
  lookup service.
- **Idempotent-ish replays** via a fresh `customerOrderNumber` (bump/random) so the same
  captured order can be safely re-run.
- **Deterministic artifacts** in `results/` make CLI runs auditable and shareable in tickets
  (with `--redact-password` for safe curl sharing).
```
