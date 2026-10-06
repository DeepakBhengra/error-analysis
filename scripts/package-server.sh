#!/usr/bin/env bash
# Build web/dist (needs Node.js here) and zip a server package that does not need Node.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

STAGE="${TMPDIR:-/tmp}/error-analysis-server-pack"
OUT="${1:-$ROOT/error-analysis-server.zip}"

if ! command -v npm >/dev/null 2>&1; then
  echo "Node.js/npm is required on this machine to build web/dist once." >&2
  echo "The hosting server will not need Node.js." >&2
  exit 1
fi

if [[ ! -d "$ROOT/web/node_modules" ]]; then
  (cd "$ROOT/web" && npm install)
fi
(cd "$ROOT/web" && npm run build)

if [[ ! -f "$ROOT/web/dist/index.html" ]]; then
  echo "UI build failed: web/dist/index.html is missing." >&2
  exit 1
fi

rm -rf "$STAGE"
mkdir -p "$STAGE/error-analysis-server"

# Files the server needs. No .env, .venv, node_modules, or tests.
tar -C "$ROOT" -cf - \
  --exclude '.env' \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude 'venv' \
  --exclude 'logs' \
  --exclude 'results' \
  --exclude 'web/node_modules' \
  --exclude 'web/src' \
  --exclude 'web/public' \
  --exclude 'tests' \
  --exclude 'scripts' \
  --exclude '*.zip' \
  --exclude '__pycache__' \
  --exclude '*.py[cod]' \
  --exclude '*.egg-info' \
  src \
  pyproject.toml \
  requirements-runtime.txt \
  .env.example \
  HOSTING.md \
  start-server.sh \
  web/dist \
  web/package.json \
  | tar -C "$STAGE/error-analysis-server" -xf -

# Keep start-server executable inside the zip.
chmod +x "$STAGE/error-analysis-server/start-server.sh"

rm -f "$OUT"
(
  cd "$STAGE"
  zip -qr "$OUT" error-analysis-server
)

echo "Wrote $OUT"
echo "Send this zip to the hosting team. They need Python 3.10+, not Node.js."
echo "Tell them to set ERROR_ANALYSIS_HOST=0.0.0.0 and ERROR_ANALYSIS_PORT=<assigned port>."
