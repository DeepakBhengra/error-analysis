# Host this application on a server (no Node.js, no venv)

The browser UI is static files in `web/dist`. Python libraries are copied into `vendor/`.
The hosting server only needs **system `python3` (3.10+)** and a port.

## What to send

On a machine that matches the server OS/CPU (for example both Linux x86_64) and has Node.js:

```bash
./scripts/package-server.sh
```

Send `error-analysis-server.zip`. Do **not** send `.env`.

The zip already contains:

- App source (`src/`)
- Built UI (`web/dist`)
- Python libraries (`vendor/` — FastAPI, uvicorn, httpx, …)
- `start-server.sh` and `.env.example`

The server team does **not** run `python3 -m venv` or `pip install`.

Package on the same kind of machine the server is. Windows-built `vendor/` will not run on Linux, and the Python minor version should be close (3.12 packaged → 3.12 on the server is safest).

## Server steps

```bash
unzip error-analysis-server.zip
cd error-analysis-server
cp .env.example .env
# Edit .env: Datadog token/keys, ORDER_CREATE_USERNAME / PASSWORD

export ERROR_ANALYSIS_HOST=0.0.0.0
export ERROR_ANALYSIS_PORT=9000   # port the server assigns
./start-server.sh
```

Open `http://<server-host>:9000`.

## Server requirements

| Item | Required |
|------|----------|
| System `python3` 3.10+ | Yes |
| `python3 -m venv` / pip on the server | **No** (modules are in `vendor/`) |
| Node.js / npm | **No** |
| Database | No |
| Port | `ERROR_ANALYSIS_PORT` |
| Outbound HTTPS to Datadog | Yes |
| Outbound access to Ingram Order Create `:9043` | Yes for RUN / Re-Submit (corporate network/VPN) |

## Optional

- Error-code popup needs the separate Legacy COBOL Error Scanner (`LOOKUP_API_URL`). Search/replay work without it.
- Put HTTPS in front with nginx/IIS if users reach this over the network.
- The process must be able to write `.env` if anyone uses Settings, and `logs/` for application logs.
