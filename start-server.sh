#!/usr/bin/env bash
# Start API + built UI using bundled vendor/ modules.
# No Node.js and no virtualenv on the server when vendor/ is present.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

HOST="${ERROR_ANALYSIS_HOST:-0.0.0.0}"
PORT="${ERROR_ANALYSIS_PORT:-8010}"
export ERROR_ANALYSIS_HOST="$HOST"
export ERROR_ANALYSIS_PORT="$PORT"

if [[ ! -f "$ROOT/web/dist/index.html" ]]; then
  echo "Missing web/dist/index.html." >&2
  echo "Build the UI on a machine with Node.js, then send web/dist with this app." >&2
  exit 1
fi

if [[ ! -f "$ROOT/.env" ]]; then
  echo "Missing .env — copy .env.example to .env and set Datadog / Order Create credentials." >&2
  exit 1
fi

if command -v python3 >/dev/null 2>&1; then
  PYTHON="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON="python"
elif command -v py >/dev/null 2>&1; then
  PYTHON="py"
elif [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
else
  echo "Python 3.10+ is required (system python3/python is enough)." >&2
  exit 1
fi

PYTHONPATH_PARTS=("$ROOT/src")
if [[ -d "$ROOT/vendor" ]]; then
  PYTHONPATH_PARTS+=("$ROOT/vendor")
fi
export PYTHONPATH="$(IFS=:; echo "${PYTHONPATH_PARTS[*]}")${PYTHONPATH:+:$PYTHONPATH}"

if ! "$PYTHON" -c "import fastapi, uvicorn, httpx" 2>/dev/null; then
  echo "Python packages were not found." >&2
  echo "Send a package built with ./scripts/package-server.sh (it includes vendor/)." >&2
  echo "The server should not need python3 -m venv when vendor/ is present." >&2
  exit 1
fi

echo "Starting Error Analysis on http://${HOST}:${PORT}"
exec "$PYTHON" -m uvicorn error_analysis.api:app --host "$HOST" --port "$PORT"
