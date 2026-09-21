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
  uv pip install --python "$VENV/bin/python" "django==6.0.*"
fi

"$VENV/bin/python" demo/manage.py migrate --noinput
"$VENV/bin/python" demo/manage.py seed_demo

echo
echo "Demo admin:  http://127.0.0.1:${PORT}/admin/"
echo "Accounts:    demo/demo (superuser)   operator/operator (cannot purge)"
echo "Database:    ${DEMO_DB} (disposable, generated data only)"
echo
exec "$VENV/bin/python" demo/manage.py runserver "127.0.0.1:${PORT}"
