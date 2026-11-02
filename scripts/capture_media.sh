#!/usr/bin/env bash
# Capture docs/media (the README GIFs, the REPL page screenshots, light and dark, and the manifest)
# from real journeys on the demo data.
# Run it after the gate passed, in the same runtime (docker/ci.Dockerfile), and commit the result.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$ROOT/.uvcache}"
VENV="$ROOT/.venvs/capture"
rm -rf "$ROOT/dist" "$ROOT/artifacts/capture" "$ROOT/artifacts/browser-db"
for project in . packages/*; do uv build --quiet --wheel --out-dir "$ROOT/dist" "$project"; done
[ -x "$VENV/bin/python" ] || uv venv --python 3.13 "$VENV" >/dev/null
uv pip install --python "$VENV/bin/python" --quiet "django==6.0.*" "django-tasks-db==0.13.0" \
  "channels==4.3.2" "daphne==4.2.3" "ipython==9.17.1" "playwright==1.63.0" "pillow==12.0.0"
uv pip install --python "$VENV/bin/python" --quiet --no-deps --reinstall --no-cache "$ROOT"/dist/*.whl
ADMIN_EXTENSIONS_ARTIFACTS="$ROOT/artifacts/capture-run" "$VENV/bin/python" scripts/capture_media.py
