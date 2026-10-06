#!/usr/bin/env bash
# Build web/dist and vendor Python modules, then zip a server package.
# The hosting server needs system python3 only — not Node.js and not a venv.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

STAGE="${TMPDIR:-/tmp}/error-analysis-server-pack"
OUT="${1:-$ROOT/error-analysis-server.zip}"
PACKAGER_PYTHON="${PACKAGER_PYTHON:-python3}"

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

# App files. No .env, .venv, node_modules, or tests.
tar -C "$ROOT" -cf - \
  --exclude '.env' \
  --exclude '.git' \
  --exclude '.venv' \
  --exclude 'venv' \
  --exclude 'vendor' \
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
  requirements-vendor.txt \
  .env.example \
  HOSTING.md \
  start-server.sh \
  web/dist \
  web/package.json \
  | tar -C "$STAGE/error-analysis-server" -xf -

chmod +x "$STAGE/error-analysis-server/start-server.sh"

echo "Vendoring Python modules into the zip (so the server skips venv)..."
"$PACKAGER_PYTHON" -m pip install \
  --disable-pip-version-check \
  --no-compile \
  -r "$ROOT/requirements-vendor.txt" \
  -t "$STAGE/error-analysis-server/vendor"
# Scripts in vendor/bin point at this machine's Python; start-server uses python3 -m.
rm -rf "$STAGE/error-analysis-server/vendor/bin"
find "$STAGE/error-analysis-server/vendor" -type d -name '__pycache__' -prune -exec rm -rf {} +

rm -f "$OUT"
(
  cd "$STAGE"
  zip -qr "$OUT" error-analysis-server
)

echo "Wrote $OUT"
echo "Send this zip to the hosting team."
echo "They need system python3 (same OS/arch as this packager). No Node.js, no venv."
echo "ERROR_ANALYSIS_HOST=0.0.0.0 ERROR_ANALYSIS_PORT=<assigned-port> ./start-server.sh"
