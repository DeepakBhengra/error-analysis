# Host this application on a server (no Node.js)

The browser UI is static files in `web/dist`. **Node.js is only needed to build those files once**, on a developer machine. The hosting server runs **Python 3.10+** only.

## What to send the server team

From a machine that **does** have Node.js, create the package:

```bash
./scripts/package-server.sh
```

That writes `error-analysis-server.zip`. Send the zip. Do **not** send `.env` (it has secrets). Send `.env.example` and have them fill credentials on the server.

The zip includes:

- Python source (`src/`, `pyproject.toml`)
- Prebuilt UI (`web/dist`)
- `requirements-runtime.txt`
- `start-server.sh`
- `.env.example`

It does **not** include Node.js, `web/node_modules`, `.venv`, or `.env`.

## Server requirements

| Item | Required |
|------|----------|
| Python 3.10 or newer | Yes |
| `pip` / `venv` | Yes (to install FastAPI, uvicorn, httpx, …) |
| Node.js / npm | **No** (UI is already built) |
| Database | No |
| Port | Whatever the server assigns (`ERROR_ANALYSIS_PORT`) |
| Outbound HTTPS to Datadog (`api.us5.datadoghq.com`) | Yes (log search) |
| Outbound access to Ingram Order Create UAT/QA (`*:9043`) | Yes for RUN / Re-Submit (usually corporate network/VPN) |

Python still needs a virtualenv **or** a system install of the packages in `requirements-runtime.txt`. The UI build does not replace Python.

## Server install

```bash
unzip error-analysis-server.zip
cd error-analysis-server

python3 -m venv .venv
.venv/bin/pip install -r requirements-runtime.txt

cp .env.example .env
# Edit .env: Datadog token/keys, ORDER_CREATE_USERNAME / PASSWORD
```

If the server cannot reach PyPI, build a `wheels/` folder on a machine that can, and send that too:

```bash
pip download -r requirements-runtime.txt -d wheels
```

On the server:

```bash
.venv/bin/pip install --no-index --find-links wheels -r requirements-runtime.txt
```

## Start (server assigns the port)

```bash
export ERROR_ANALYSIS_HOST=0.0.0.0
export ERROR_ANALYSIS_PORT=9000   # use the port the server gives you
./start-server.sh
```

Or:

```bash
.venv/bin/uvicorn error_analysis.api:app --host 0.0.0.0 --port 9000
```

Open `http://<server-host>:9000`. Leave the process running (systemd, service account, etc.).

`0.0.0.0` means “accept connections from other machines”. `127.0.0.1` is laptop-only.

## Optional

- Error-code popup needs the separate Legacy COBOL Error Scanner. Point `LOOKUP_API_URL` at it, or skip it; search/replay still work.
- Put HTTPS in front with nginx/IIS if users reach this over the network.
- The process must be able to write `.env` if anyone uses the Settings page, and `logs/` for application logs.
