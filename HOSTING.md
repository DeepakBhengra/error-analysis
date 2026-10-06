# Host this application on a server (no Node.js, no venv)

Two machines:

1. **Your machine** (has Node.js and Python) — builds the UI and **puts the Python libraries inside the zip**.
2. **The server** (system `python3` only) — unzips and starts. No Node.js, no `venv`, no `pip`.

Package on the **same OS and CPU** as the server (Linux x86_64 → Linux x86_64). A Windows zip will not run on Linux. Use a Python version close to the server (3.12 → 3.12 is safest).

---

## Part A — Put the Python libraries inside the zip (your machine)

These steps create `error-analysis-server.zip` with `vendor/` (FastAPI, uvicorn, httpx, …).

1. Install **Python 3.10+** and **Node.js + npm** on this machine (not on the server).
2. Open a terminal in the project root (the folder that contains `scripts/package-server.sh`).
3. Confirm you can reach PyPI (the script downloads the Python libraries here, once):

   ```bash
   python3 --version
   python3 -m pip --version
   npm --version
   ```

4. Make the packager executable (Linux/macOS):

   ```bash
   chmod +x scripts/package-server.sh start-server.sh
   ```

5. Build the UI and copy the Python libraries into the zip:

   ```bash
   ./scripts/package-server.sh
   ```

   That single command:

   - runs `npm install` / `npm run build` → `web/dist`
   - runs `pip install -r requirements-vendor.txt -t vendor/`
   - zips app + `web/dist` + `vendor/` → `error-analysis-server.zip`

   Optional output path:

   ```bash
   ./scripts/package-server.sh /path/to/error-analysis-server.zip
   ```

6. Check the zip actually contains the libraries and the UI (and not secrets):

   ```bash
   unzip -l error-analysis-server.zip | grep -E 'vendor/fastapi/__init__.py|web/dist/index.html|\.env$'
   ```

   You should see `vendor/fastapi/...` and `web/dist/index.html`. You should **not** see a `.env` file.

7. Send **`error-analysis-server.zip`** to the hosting team. Also send this file (`HOSTING.md`) if they do not have the repo.

8. Do **not** send `.env`. Credentials are filled on the server in Part B.

---

## Part B — Run on the server (no venv)

The zip already has `vendor/`. The server does not run `python3 -m venv` or `pip install`.

1. Copy `error-analysis-server.zip` onto the server.
2. Unzip and enter the folder:

   ```bash
   unzip error-analysis-server.zip
   cd error-analysis-server
   ```

3. Confirm system Python exists (3.10+):

   ```bash
   python3 --version
   ```

4. Create credentials from the example (do this on the server, not in the zip you were sent):

   ```bash
   cp .env.example .env
   ```

   Edit `.env` and set at least:

   - `DD_ACCESS_TOKEN` **or** `DD_API_KEY` + `DD_APP_KEY`
   - `DD_SITE=us5.datadoghq.com`
   - `ORDER_CREATE_USERNAME`
   - `ORDER_CREATE_PASSWORD`

5. Make the start script executable:

   ```bash
   chmod +x start-server.sh
   ```

6. Bind to all interfaces and the **port the server assigns**:

   ```bash
   export ERROR_ANALYSIS_HOST=0.0.0.0
   export ERROR_ANALYSIS_PORT=9000
   ./start-server.sh
   ```

   Replace `9000` with the real assigned port.

7. Open `http://<server-hostname-or-ip>:9000`. Leave the process running.

`start-server.sh` loads the app from `src/` and the libraries from `vendor/` using `PYTHONPATH`. That is why there is no virtualenv on the server.

---

## Server requirements

| Item | Required |
|------|----------|
| System `python3` 3.10+ | Yes |
| `python3 -m venv` / pip on the server | **No** (`vendor/` is in the zip) |
| Node.js / npm | **No** |
| Database | No |
| Port | `ERROR_ANALYSIS_PORT` |
| Outbound HTTPS to Datadog | Yes |
| Outbound access to Ingram Order Create `:9043` | Yes for RUN / Re-Submit (corporate network/VPN) |

---

## Optional

- Error-code popup needs the separate Legacy COBOL Error Scanner (`LOOKUP_API_URL`). Search/replay work without it.
- Put HTTPS in front with nginx/IIS if users reach this over the network.
- The process must be able to write `.env` if anyone uses Settings, and `logs/` for application logs.
