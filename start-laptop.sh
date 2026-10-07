#!/usr/bin/env bash
# Run the packaged app on a laptop that has only Python (no Node.js, no venv).
# Requires web/dist and vendor/ from ./scripts/package-server.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
export ERROR_ANALYSIS_HOST="${ERROR_ANALYSIS_HOST:-127.0.0.1}"
export ERROR_ANALYSIS_PORT="${ERROR_ANALYSIS_PORT:-8010}"
exec "$ROOT/start-server.sh"
