#!/usr/bin/env bash
# Run the task-backend spike for one lane against disposable containers.
#
#   bash spikes/task_backends/run.sh db60|db52|db61|celery60 [postgres|sqlite]
#
# Containers are started with --rm on 127.0.0.1 random ports under a unique
# deadmin-spike-* name and removed on exit. Output: artifacts/task-backend-spike/<lane>-<db>/.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HERE="$ROOT/spikes/task_backends"
LANE="${1:?lane: db60|db52|db61|celery60}"
DB="${2:-postgres}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$ROOT/.uvcache}"

case "$LANE" in
  db60)     REQS=("django==6.0.*" "django-tasks-db==0.13.0") ;;
  db52)     REQS=("django==5.2.*" "django-tasks-db[compat]==0.13.0") ;;
  db61)     REQS=("django==6.1.*" "django-tasks-db==0.13.0") ;;
  celery60) REQS=("django==6.0.*" "django-tasks-celery[celery]==0.1.1" "redis==8.*") ;;
  *) echo "unknown lane $LANE" >&2; exit 2 ;;
esac
[ "$DB" = postgres ] && REQS+=("psycopg[binary]==3.*")
[[ "$LANE" == celery* ]] && export SPIKE_BACKEND=celery || export SPIKE_BACKEND=db

VENV="$ROOT/.venvs/spike-$LANE"
PY="$VENV/bin/python"
if [ ! -x "$PY" ]; then
  uv venv -q --python 3.13 "$VENV"
fi
uv pip install -q --python "$PY" "${REQS[@]}"

OUT="$ROOT/artifacts/task-backend-spike/$LANE-$DB"
rm -rf "$OUT"
mkdir -p "$OUT"
NAME="deadmin-spike-$LANE-$DB-$$"
CONTAINERS=()

cleanup() {
  for c in "${CONTAINERS[@]}"; do docker rm -f "$c" >/dev/null 2>&1 || true; done
  echo "removed containers: ${CONTAINERS[*]:-none}" | tee -a "$OUT/environment.txt"
}
trap cleanup EXIT

port_of() { docker port "$1" "$2" | head -1 | sed 's/.*://'; }

if [ "$DB" = postgres ]; then
  docker run -d --rm --name "$NAME-pg" -p 127.0.0.1::5432 \
    -e POSTGRES_USER=spike -e POSTGRES_PASSWORD=spike -e POSTGRES_DB=spike \
    postgres:16-alpine >/dev/null
  CONTAINERS+=("$NAME-pg")
  for _ in $(seq 60); do
    docker exec "$NAME-pg" pg_isready -U spike -d spike -h 127.0.0.1 >/dev/null 2>&1 && break
    sleep 0.5
  done
  export SPIKE_PG="127.0.0.1:$(port_of "$NAME-pg" 5432)"
else
  export SPIKE_SQLITE="$OUT/spike.sqlite3"
fi

if [ "$SPIKE_BACKEND" = celery ]; then
  docker run -d --rm --name "$NAME-redis" -p 127.0.0.1::6379 \
    redis:7-alpine redis-server --save "" --appendonly no >/dev/null
  CONTAINERS+=("$NAME-redis")
  for _ in $(seq 60); do
    docker exec "$NAME-redis" redis-cli ping 2>/dev/null | grep -q PONG && break
    sleep 0.5
  done
  export SPIKE_REDIS="redis://127.0.0.1:$(port_of "$NAME-redis" 6379)"
fi

{
  echo "lane          $LANE ($DB)"
  echo "date          $(date -Is)"
  echo "git           $(git -C "$ROOT" rev-parse --short HEAD)"
  echo "python        $("$PY" --version)"
  for c in "${CONTAINERS[@]}"; do
    echo "container     $c $(docker inspect -f '{{.Config.Image}} {{.Image}}' "$c")"
  done
  echo "--- uv pip freeze"
  uv pip freeze --python "$PY" 2>/dev/null
} > "$OUT/environment.txt"

cd "$HERE"
"$PY" manage.py migrate --noinput > "$OUT/migrate.txt" 2>&1
"$PY" manage.py check > "$OUT/check.txt" 2>&1 || true
"$PY" orchestrate.py --lane "$LANE-$DB" --python "$PY" --out "$OUT"
echo "orchestrator exit=$?" | tee -a "$OUT/environment.txt"
