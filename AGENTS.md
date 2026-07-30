# AGENTS.md

## Cursor Cloud specific instructions

This repo has three faces over one Python package (`src/error_analysis/`): a CLI
(`error-analysis`), a FastAPI backend (`error-analysis-api`), and a React/Vite web UI
(`web/`). Standard setup/run commands live in `README.md`; below are only the
non-obvious caveats for this environment.

### Services

| Service | Dir | Start (dev) | Port | Notes |
|---|---|---|---|---|
| FastAPI backend | repo root | `. .venv/bin/activate && ERROR_ANALYSIS_RELOAD=1 error-analysis-api` | 8010 | Port is hardcoded in `api.py:main()`. Set `ERROR_ANALYSIS_RELOAD=1` for hot reload (the `error-analysis-api` script does not reload by default). |
| Web UI (Vite dev) | `web/` | `npm run dev` | 5173 | Vite proxies `/api` → `http://127.0.0.1:8010`, so start the backend first. |

The `.ps1` launchers and `Start Error Analysis.bat` are Windows-only; on Linux use the commands above.

### Non-obvious caveats

- Vite dev server binds to `localhost` (IPv6 `::1`). Health-check it with
  `curl http://localhost:5173/`, not `127.0.0.1` (which refuses the connection).
- Credentials are loaded lazily per-request, so both the backend and UI start with no
  real credentials. Real Datadog search / Order Create replay needs `DD_API_KEY`,
  `DD_APP_KEY`, and `ORDER_CREATE_USERNAME`/`ORDER_CREATE_PASSWORD` in `.env`
  (copy `.env.example`); missing values surface as HTTP 500/400 only when a data endpoint is hit.
- Offline-testable flows (no external services): `pytest`, CLI `error-analysis build-order-curl --from-file <records.json>`, backend `GET/PUT /api/settings`, and the web Settings page.
- The web UI has NO committed lockfile originally; the root `.gitignore` blanket-ignores
  `*.json`. `web/package.json`, `web/tsconfig*.json`, and `web/package-lock.json` are
  explicitly un-ignored so the Vite/TS setup is reproducible. Keep those un-ignore rules
  when editing `.gitignore`, and remember any new root-level `*.json` is git-ignored by default.
- Web lint: `npm run lint` (oxlint, zero-config). Web build/type-check: `npm run build` (`tsc -b && vite build`).
