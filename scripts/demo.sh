#!/usr/bin/env bash
# Start the disposable demo admin on loopback only. Local evaluation, never deployed.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PORT="${DEMO_PORT:-8765}"
VENV="$ROOT/.venvs/demo"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$ROOT/.uvcache}"
export DEMO_DB="${DEMO_DB:-$ROOT/demo/demo.sqlite3}"

if [ ! -x "$VENV/bin/python" ]; then
  uv venv --python 3.13 "$VENV"
fi
# django-tasks-db is the command runner's queue; the rest of the demo does not need it.
uv pip install --quiet --python "$VENV/bin/python" "django==6.0.*" "django-tasks-db==0.13.0"

"$VENV/bin/python" demo/manage.py migrate --noinput
"$VENV/bin/python" demo/manage.py seed_demo

# The worker that runs commands launched from /admin/commands/. It lives exactly as long
# as this script: stopped (SIGTERM, which lets a running command finish) on exit.
"$VENV/bin/python" demo/manage.py db_worker --backend commands --no-reload &
WORKER_PID=$!
trap 'kill -TERM "$WORKER_PID" 2>/dev/null; wait "$WORKER_PID" 2>/dev/null' EXIT

echo
echo "Demo admin:  http://127.0.0.1:${PORT}/admin/"
echo "Commands:    http://127.0.0.1:${PORT}/admin/commands/  (worker pid ${WORKER_PID})"
echo "Accounts:    demo/demo (superuser)   operator/operator (cannot purge or run commands)"
echo "Database:    ${DEMO_DB} (disposable, generated data only)"
echo
"$VENV/bin/python" demo/manage.py runserver "127.0.0.1:${PORT}"
