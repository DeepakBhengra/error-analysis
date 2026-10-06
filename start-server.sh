#!/usr/bin/env bash
# Start API + built UI. The server does not need Node.js when web/dist exists.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

HOST="${ERROR_ANALYSIS_HOST:-0.0.0.0}"
PORT="${ERROR_ANALYSIS_PORT:-8010}"
export ERROR_ANALYSIS_HOST="$HOST"
export ERROR_ANALYSIS_PORT="$PORT"

if [[ ! -f "$ROOT/web/dist/index.html" ]]; then
  echo "Missing web/dist/index.html." >&2
  echo "Build the UI on a machine with Node.js (cd web && npm install && npm run build)," >&2
  echo "then copy web/dist onto this server. Node.js is not required here." >&2
  exit 1
fi

if [[ ! -f "$ROOT/.env" ]]; then
  echo "Missing .env — copy .env.example to .env and set Datadog / Order Create credentials." >&2
  exit 1
fi

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="python3"
else
  echo "Python 3.10+ is required." >&2
  exit 1
fi

export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

echo "Starting Error Analysis on http://${HOST}:${PORT}"
exec "$PYTHON" -m uvicorn error_analysis.api:app --host "$HOST" --port "$PORT"
