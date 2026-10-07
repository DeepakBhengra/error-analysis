# Host this application without Node.js (server or another laptop)

Two machines:

1. **Your machine** (has Node.js and Python) — builds the UI and **puts the Python libraries inside the zip**.
2. **Their machine** (system Python only) — a server or another laptop. Unzip and start. No Node.js, no `venv`, no `pip`.

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

## Part C — Another laptop that only has Python (no Node.js)

Same zip as Part A. The other person does **not** install Node.js, npm, or a virtualenv. They only need **Python 3.10+**.

Build the zip on the **same kind of laptop** they have:

| Their laptop | You must run `./scripts/package-server.sh` on |
|--------------|-----------------------------------------------|
| Windows      | Windows (same 64-bit, similar Python 3.12)    |
| Linux        | Linux                                         |
| macOS        | macOS                                         |

A Linux zip will not start on a Windows laptop (`vendor/` contains OS-specific files).

### On their laptop (detailed)

Do this **on their laptop**, not on yours. They need Python 3.10+ already installed. They do not install Node.js.

#### 1. Copy the zip onto their laptop

- Email, USB, OneDrive, or a shared folder is fine.
- Put `error-analysis-server.zip` somewhere easy, for example:
  - Windows: `C:\Users\<their-name>\Downloads\`
  - Linux/macOS: `~/Downloads/`

#### 2. Unzip it

**Windows**

1. Open File Explorer and go to Downloads.
2. Right-click `error-analysis-server.zip` → **Extract All…**
3. Click **Extract** (keep the suggested folder).
4. You should get a folder named `error-analysis-server`.
5. Open that folder. You should see at least:
   - `start-laptop.ps1`
   - `Start Error Analysis Laptop.bat`
   - `.env.example`
   - `src`
   - `vendor`
   - `web` (inside it, `dist`)

If Windows hid the `.zip` ending, the file still opens with Extract All.

**Linux / macOS**

1. Open a terminal.
2. Run:

   ```bash
   cd ~/Downloads
   unzip error-analysis-server.zip
   cd error-analysis-server
   ```

3. Confirm files:

   ```bash
   ls
   ```

   You should see `start-laptop.sh`, `.env.example`, `src`, `vendor`, `web`.

#### 3. Create `.env` from the example

This file holds Datadog and Order Create passwords. Create it on **their** laptop. Do not copy your `.env`.

**Windows (File Explorer)**

1. In the `error-analysis-server` folder, click **View** → enable **File name extensions** (so you can see `.example`).
2. Right-click `.env.example` → **Copy**.
3. Right-click empty space in the same folder → **Paste**.
4. Right-click the copy → **Rename**.
5. Name it exactly `.env` (dot, then `env`, no `.txt` and no `.example`).
   - If Windows says “If you change a file name extension, the file might become unusable”, click **Yes**.
   - If the file becomes `.env.txt`, rename again and remove `.txt`.
6. Right-click `.env` → **Open with** → **Notepad**.

**Linux / macOS**

```bash
cp .env.example .env
nano .env
```

(`nano` is optional; any text editor is fine.)

#### 4. Fill credentials in `.env`

Leave the other lines as they are. Change only these.

**Datadog (pick one option, not both):**

- Option A (preferred): set `DD_ACCESS_TOKEN` to their Personal/Service Access Token (logs read). Leave `DD_API_KEY` / `DD_APP_KEY` as placeholders or empty.
- Option B: set `DD_API_KEY` and `DD_APP_KEY` (app key needs `logs_read_data`). Leave `DD_ACCESS_TOKEN` empty.

Keep:

```env
DD_SITE=us5.datadoghq.com
```

**Order Create replay (needed for RUN / Re-Submit):**

```env
ORDER_CREATE_USERNAME=their_username
ORDER_CREATE_PASSWORD=their_password
```

Example of a filled block (fake values):

```env
DD_ACCESS_TOKEN=their_datadog_token_here
DD_API_KEY=
DD_APP_KEY=
DD_SITE=us5.datadoghq.com
ORDER_CREATE_USERNAME=APPIMEAI
ORDER_CREATE_PASSWORD=secret
```

Save the file and close the editor.

They can skip Order Modify and lookup lines for a first run. Error-code popup needs the COBOL scanner later; search still works without it.

#### 5. Confirm Python is installed

**Windows** — open Command Prompt or PowerShell:

```powershell
python --version
```

If that fails:

```powershell
py --version
```

You want `Python 3.10` or newer.

**Linux / macOS:**

```bash
python3 --version
```

#### 6. Start the app

**Windows**

1. Stay in the `error-analysis-server` folder in File Explorer.
2. Double-click `Start Error Analysis Laptop.bat`.
3. A black window opens. Wait until it prints something like:

   `Starting Error Analysis on http://127.0.0.1:8010`

4. Leave that window open. Closing it stops the app.

If double-click fails, open PowerShell **in that folder** (File Explorer address bar: type `powershell` and Enter) and run:

```powershell
.\start-laptop.ps1
```

**Linux / macOS**

```bash
chmod +x start-laptop.sh start-server.sh
./start-laptop.sh
```

Leave the terminal open. You should see `Starting Error Analysis on http://127.0.0.1:8010`.

#### 7. Open the UI

1. Open Chrome or Edge.
2. Go to http://127.0.0.1:8010
3. Use Search / RUN as usual.

To stop: go to the black window / terminal, press **Ctrl+C**, then you can close it.

They still need internet to Datadog. For RUN / Re-Submit they need corporate VPN so the laptop can reach Ingram Order Create hosts.

---

## Their machine requirements

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
