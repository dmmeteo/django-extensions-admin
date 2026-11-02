#!/usr/bin/env bash
# The README quickstart, as written, with ordinary pip in a fresh venv and a fresh copy of the
# tracked tree, then a new `startproject` that adopts [buttons,repl] as docs/repl.md says, a
# login, a REPL session over HTTP, and a server restart that ends it.
#   bash scripts/ci/quickstart.sh <python> <artifacts dir>
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYTHON="$1"; OUT="$2"
WORK="$(mktemp -d)"
trap 'kill "$(cat "$WORK/daphne.pid" 2>/dev/null)" 2>/dev/null || true; rm -rf "$WORK"' EXIT
mkdir -p "$OUT" "$WORK/checkout"
# The checkout README's clone produces: the tracked files, no build output, no venvs.
(cd "$ROOT" && tar --exclude=./.venvs --exclude=./dist --exclude=./artifacts --exclude=./.uvcache -cf - .) \
  | tar -C "$WORK/checkout" -xf -
cd "$WORK/checkout"

# README "Quickstart", verbatim after the clone.
"$PYTHON" -m venv .venv && . .venv/bin/activate
pip install --quiet build
for project in . packages/*; do python -m build --wheel --outdir dist "$project" >/dev/null; done
pip install --quiet "Django>=5.2,<7" "channels>=4.1"
pip install --quiet --no-index --find-links dist "django-extensions-admin[buttons,repl]"
pip install --quiet "daphne==4.2.3"
pip list --format=freeze | grep -iE '^(django|channels|daphne)' | tee "$OUT/quickstart-installed.txt"

cd "$WORK"
django-admin startproject mysite
cd mysite
python - <<'PY'
from pathlib import Path
settings = Path("mysite/settings.py")
text = settings.read_text().replace(
    "INSTALLED_APPS = [\n",
    'INSTALLED_APPS = [\n    "daphne",\n    "django_extensions_admin",\n'
    '    "django_extensions_admin.panel",\n    "django_extensions_admin.repl",\n',
)
text += (
    '\nASGI_APPLICATION = "mysite.asgi.application"\n'
    'ALLOWED_HOSTS = ["127.0.0.1"]\n'
    'ADMIN_EXTENSIONS = {"REPL_ENABLED": True, "REPL_LOCK_PATH": str(BASE_DIR / "repl.lock")}\n'
)
settings.write_text(text)
Path("mysite/urls.py").write_text(
    "from django.contrib import admin\nfrom django.urls import include, path\n\n"
    "urlpatterns = [\n"
    '    path("admin/repl/", include("django_extensions_admin.repl.urls")),\n'
    '    path("admin/", admin.site.urls),\n]\n'
)
Path("mysite/asgi.py").write_text(
    "import os\n\nfrom django.core.asgi import get_asgi_application\n\n"
    'os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mysite.settings")\n'
    "django_asgi_app = get_asgi_application()\n\n"
    "from channels.auth import AuthMiddlewareStack  # noqa: E402\n"
    "from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402\n"
    "from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402\n"
    "from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler  # noqa: E402\n\n"
    "from django_extensions_admin.repl.routing import websocket_urlpatterns  # noqa: E402\n\n"
    "application = ProtocolTypeRouter({\n"
    '    "http": ASGIStaticFilesHandler(django_asgi_app),\n'
    '    "websocket": AllowedHostsOriginValidator(AuthMiddlewareStack(URLRouter(websocket_urlpatterns))),\n'
    "})\n"
)
PY
python manage.py check --fail-level WARNING
python manage.py migrate --noinput >/dev/null
PASSWORD="$(python -c 'import secrets; print(secrets.token_urlsafe(18))')"
DJANGO_SUPERUSER_PASSWORD="$PASSWORD" python manage.py createsuperuser --noinput --username owner --email owner@example.invalid
PORT="$(python -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"
serve() {
  daphne -b 127.0.0.1 -p "$PORT" mysite.asgi:application >>"$OUT/quickstart-daphne.log" 2>&1 &
  echo $! > "$WORK/daphne.pid"
}
serve
QUICKSTART_PASSWORD="$PASSWORD" python - "$PORT" "$WORK/daphne.pid" "$OUT" <<'PY'
import http.cookiejar, json, os, re, signal, subprocess, sys, time, urllib.error, urllib.request
from pathlib import Path

port, pid_file, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
base = f"http://127.0.0.1:{port}"
jar = http.cookiejar.CookieJar()
browser = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
anonymous = urllib.request.build_opener()


def wait():
    for _ in range(150):
        try:
            return anonymous.open(f"{base}/admin/login/", timeout=2).read()
        except OSError:
            time.sleep(0.2)
    raise SystemExit("daphne did not answer")


def call(opener, method, path, body=None):
    token = next((c.value for c in jar if c.name == "csrftoken"), "")
    request = urllib.request.Request(f"{base}{path}", method=method, data=body,
                                     headers={"X-CSRFToken": token, "Referer": f"{base}/admin/"})
    if body is not None and not isinstance(body, bytes):
        request.data = json.dumps(body).encode()
        request.add_header("Content-Type", "application/json")
    try:
        response = opener.open(request, timeout=10)
        return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


wait()
assert call(anonymous, "GET", "/admin/repl/state/")[0] == 401, "anonymous must get 401"
page = browser.open(f"{base}/admin/login/").read().decode()
token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page)[1]
form = urllib.parse.urlencode({"csrfmiddlewaretoken": token, "username": "owner",
                               "password": os.environ["QUICKSTART_PASSWORD"], "next": "/admin/"}).encode()
status, index = call(browser, "POST", "/admin/login/?next=/admin/", form)
assert status == 200 and "data-admin-ext-panel-toggle" in index, "logged in, panel button rendered"
assert "Tools panel" in index and ">REPL<" not in index
status, body = call(browser, "GET", "/admin/repl/state/")
assert status == 200 and json.loads(body)["session"] is None, body
status, body = call(browser, "POST", "/admin/repl/start/", {"backend": "python"})
assert status == 201, (status, body)
session = json.loads(body)["session"]
assert Path(f"/proc/{session['pid']}").exists()
# A restart ends the session's process, and the new server has no session for the owner.
pid = int(pid_file.read_text())
os.kill(pid, signal.SIGTERM)
for _ in range(100):
    if not Path(f"/proc/{pid}").exists():
        break
    time.sleep(0.1)
for _ in range(100):
    if not Path(f"/proc/{session['pid']}").exists():
        break
    time.sleep(0.1)
assert not Path(f"/proc/{session['pid']}").exists(), "REPL process outlived the server"
(out / "quickstart-restart.txt").write_text("stopped\n")
PY
serve
QUICKSTART_PASSWORD="$PASSWORD" python - "$PORT" <<'PY'
import http.cookiejar, json, os, re, sys, time, urllib.parse, urllib.request
base = f"http://127.0.0.1:{sys.argv[1]}"
jar = http.cookiejar.CookieJar()
browser = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
for _ in range(150):
    try:
        page = browser.open(f"{base}/admin/login/", timeout=2).read().decode()
        break
    except OSError:
        time.sleep(0.2)
token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page)[1]
form = urllib.parse.urlencode({"csrfmiddlewaretoken": token, "username": "owner",
                               "password": os.environ["QUICKSTART_PASSWORD"], "next": "/admin/"}).encode()
browser.open(urllib.request.Request(f"{base}/admin/login/?next=/admin/", data=form,
                                    headers={"Referer": f"{base}/admin/"}), timeout=10).read()
state = json.loads(browser.open(f"{base}/admin/repl/state/", timeout=10).read())
assert state["session"] is None, state
print("quickstart OK: pip install from dist/, startproject, check, login, REPL start, restart ends it")
PY
