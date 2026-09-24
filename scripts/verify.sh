#!/usr/bin/env bash
# Deterministic gate for django-extensions-admin.
#
#   bash scripts/verify.sh
#
# Every stage is required. A missing tool, a missing acceptance test or any failure
# exits non-zero; nothing is skipped silently. Environments are cached by a hash of
# their requirements, so a second run is bounded.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ART="$ROOT/artifacts"
VENVS="$ROOT/.venvs"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$ROOT/.uvcache}"
export PYTHONDONTWRITEBYTECODE=1
PY_VERSION="3.13"

mkdir -p "$ART" "$ART/browser"

step() { printf '\n=== %s ===\n' "$1"; }
fail() { printf '\nGATE FAILED: %s\n' "$1" >&2; exit 1; }

# --------------------------------------------------------------------------
step "1/9 preflight"
command -v uv  >/dev/null || fail "uv is required (https://docs.astral.sh/uv/)"
command -v node >/dev/null || fail "node is required for the JavaScript syntax check"

PLAYWRIGHT_CACHE="${PLAYWRIGHT_BROWSERS_PATH:-$HOME/.cache/ms-playwright}"

{
  echo "date          $(date -Is)"
  echo "uname         $(uname -sr)"
  echo "uv            $(uv --version)"
  echo "node          $(node --version)"
} | tee "$ART/versions.txt"

# --------------------------------------------------------------------------
# ensure_env <name> <requirement...> - build the venv only when requirements changed.
ensure_env() {
  local name="$1"; shift
  local venv="$VENVS/$name"
  local stamp="$venv/.stamp"
  local want
  want="$(printf '%s\n' "py$PY_VERSION" "$@" | sort | md5sum | cut -d' ' -f1)"
  if [ -x "$venv/bin/python" ] && [ -f "$stamp" ] && [ "$(cat "$stamp")" = "$want" ]; then
    return 0
  fi
  rm -rf "$venv"
  uv venv --python "$PY_VERSION" "$venv" >/dev/null
  uv pip install --python "$venv/bin/python" --quiet "$@"
  echo "$want" > "$stamp"
}

# --------------------------------------------------------------------------
step "2/9 lint"
ensure_env tools "ruff==0.14.*"
"$VENVS/tools/bin/ruff" check . 2>&1 | tee "$ART/lint-ruff-check.txt"
"$VENVS/tools/bin/ruff" format --check . 2>&1 | tee "$ART/lint-ruff-format.txt"
echo "ruff          $("$VENVS/tools/bin/ruff" --version)" >> "$ART/versions.txt"

JS_FILES=$(find src -name '*.js')
[ -n "$JS_FILES" ] || fail "no JavaScript assets found to check"
for js in $JS_FILES; do
  node --check "$js" || fail "syntax error in $js"
  echo "node --check OK $js"
done | tee "$ART/lint-js.txt"

# --------------------------------------------------------------------------
step "3/9 naming check"
# The distribution was renamed; no identifier from an earlier working name may survive.
# --exclude: this script carries the pattern itself and would match on every run.
LEFTOVERS=$(grep -rniE 'admin[-_]kit|adminkit|jsonkit' \
    --include='*.py' --include='*.html' --include='*.css' --include='*.js' \
    --include='*.toml' --include='*.md' --include='*.sh' --exclude='verify.sh' \
    src tests browser_tests demo scripts README.md ROADMAP.md pyproject.toml 2>/dev/null || true)
if [ -n "$LEFTOVERS" ]; then
  echo "$LEFTOVERS" | tee "$ART/naming.txt"
  fail "stale name found (see artifacts/naming.txt)"
fi
test -d src/django_extensions_admin || fail "package directory src/django_extensions_admin is missing"
grep -q '^name = "django-extensions-admin"' pyproject.toml || fail "distribution name is wrong"
echo "no stale identifiers; distribution django-extensions-admin, module django_extensions_admin" \
  | tee "$ART/naming.txt"

# --------------------------------------------------------------------------
step "4/9 build wheel"
rm -rf "$ROOT/dist"
uv build --wheel --out-dir "$ROOT/dist" >"$ART/build.txt" 2>&1 || { cat "$ART/build.txt"; fail "wheel build failed"; }
WHEEL=$(ls "$ROOT/dist"/*.whl)
echo "wheel         $WHEEL" >> "$ART/versions.txt"

python3 - "$WHEEL" >"$ART/wheel-contents.txt" <<'PY'
import sys, zipfile
names = zipfile.ZipFile(sys.argv[1]).namelist()
required = [
    "django_extensions_admin/static/django_extensions_admin/json-widget.css",
    "django_extensions_admin/static/django_extensions_admin/json-widget.js",
    "django_extensions_admin/static/django_extensions_admin/buttons.css",
    "django_extensions_admin/static/django_extensions_admin/filters.css",
    "django_extensions_admin/static/django_extensions_admin/choice-filters.js",
    "django_extensions_admin/templates/django_extensions_admin/change_list.html",
    "django_extensions_admin/templates/django_extensions_admin/change_form.html",
    "django_extensions_admin/templates/django_extensions_admin/buttons/toolbar.html",
    "django_extensions_admin/templates/django_extensions_admin/buttons/action_form.html",
    "django_extensions_admin/templates/django_extensions_admin/buttons/confirm.html",
    "django_extensions_admin/templates/django_extensions_admin/filters/range.html",
    "django_extensions_admin/templates/django_extensions_admin/filters/choice.html",
    "django_extensions_admin/static/django_extensions_admin/commands.css",
    "django_extensions_admin/templates/django_extensions_admin/commands/index.html",
    "django_extensions_admin/templates/django_extensions_admin/commands/launch.html",
    "django_extensions_admin/templates/django_extensions_admin/commands/result.html",
    "django_extensions_admin/static/django_extensions_admin/branding.css",
    "django_extensions_admin/templates/django_extensions_admin/branding/base_site.html",
    "django_extensions_admin/templatetags/admin_ext_branding.py",
]
missing = [name for name in required if name not in names]
print("\n".join(sorted(names)))
# The runner's backend is the application's choice: the wheel depends on Django alone.
metadata = next(n for n in names if n.endswith(".dist-info/METADATA"))
requires = [
    line.split(":", 1)[1].strip()
    for line in zipfile.ZipFile(sys.argv[1]).read(metadata).decode().splitlines()
    if line.startswith("Requires-Dist:")
]
print("Requires-Dist:", requires)
if requires != ["Django<7,>=5.2"] and requires != ["django<7,>=5.2"]:
    sys.stderr.write(f"unexpected dependencies: {requires}\n")
    raise SystemExit(1)
if missing:
    sys.stderr.write("missing from wheel:\n" + "\n".join(missing) + "\n")
    raise SystemExit(1)
PY
[ $? -eq 0 ] || fail "wheel is missing static files or templates"
echo "wheel contains every template and static asset"

# --------------------------------------------------------------------------
step "5/9 clean-install smoke"
rm -rf "$VENVS/smoke"
uv venv --python "$PY_VERSION" "$VENVS/smoke" >/dev/null
uv pip install --python "$VENVS/smoke/bin/python" --quiet "$WHEEL"
# Run from /tmp with no source on the path: this must import the installed wheel.
(cd /tmp && "$VENVS/smoke/bin/python" - <<'PY'
import sys, pathlib
import django
from django.conf import settings

settings.configure(
    INSTALLED_APPS=[
        "django_extensions_admin",
        "django.contrib.admin",
        "django.contrib.auth",
        "django.contrib.contenttypes",
        "django.contrib.messages",
        "django.contrib.sessions",
        "django.contrib.staticfiles",
    ],
    DATABASES={},
    STATIC_URL="/static/",
    SECRET_KEY="smoke",
    TEMPLATES=[
        {
            "BACKEND": "django.template.backends.django.DjangoTemplates",
            "APP_DIRS": True,
            "OPTIONS": {},
        }
    ],
)
django.setup()

import django_extensions_admin as pkg
from django_extensions_admin import ButtonsMixin, JSONReadonlyMixin, PrettyJSONWidget, button
from django_extensions_admin import DateRangeFilter, DateTimeRangeFilter, NumericRangeFilter
from django_extensions_admin import ChoiceFilter, MultipleChoiceFilter
from django_extensions_admin import admin as extensions_admin
from django_extensions_admin import readonly_json, render_json

assert (extensions_admin.button, extensions_admin.ButtonsMixin) == (button, ButtonsMixin)
assert extensions_admin.DateRangeFilter is DateRangeFilter
assert extensions_admin.MultipleChoiceFilter is MultipleChoiceFilter
# Read-only JSON brings its own stylesheet, with no editable widget and no buttons.
assert JSONReadonlyMixin.Media.css == {"all": ("django_extensions_admin/json-widget.css",)}
assert callable(readonly_json("payload"))

root = pathlib.Path(pkg.__file__).parent
assert "site-packages" in str(root), f"imported from the source tree, not the wheel: {root}"
for rel in (
    "static/django_extensions_admin/json-widget.css",
    "static/django_extensions_admin/json-widget.js",
    "static/django_extensions_admin/buttons.css",
    "static/django_extensions_admin/filters.css",
    "static/django_extensions_admin/choice-filters.js",
    "templates/django_extensions_admin/change_list.html",
    "templates/django_extensions_admin/buttons/confirm.html",
    "templates/django_extensions_admin/filters/range.html",
    "templates/django_extensions_admin/filters/choice.html",
):
    assert (root / rel).is_file(), f"missing from the installed package: {rel}"

from django.contrib.staticfiles import finders
assert finders.find("django_extensions_admin/json-widget.js"), "staticfiles cannot find the script"
from django.template.loader import get_template
get_template("django_extensions_admin/buttons/confirm.html")

# Rendering keeps integers JavaScript cannot hold; Python's are arbitrary precision.
assert "9007199254740993" in PrettyJSONWidget().format_value('{"n": 9007199254740993}')
assert "admin-ext-json-key" in render_json({"n": 1})
# Range filters are plain list_filter entries: no mixin, no setting, no registration.
for filter_class in (DateRangeFilter, DateTimeRangeFilter, NumericRangeFilter):
    assert filter_class.template == "django_extensions_admin/filters/range.html"
get_template("django_extensions_admin/filters/range.html")
# Choice filters too: one template for the dropdown and the checkbox list.
for filter_class in (ChoiceFilter, MultipleChoiceFilter):
    assert filter_class.template == "django_extensions_admin/filters/choice.html"
assert (ChoiceFilter.multiple, MultipleChoiceFilter.multiple) == (False, True)
get_template("django_extensions_admin/filters/choice.html")
assert finders.find("django_extensions_admin/choice-filters.js"), "staticfiles cannot find it"

# No Tasks package is installed here. Every feature above imported without one, and
# nothing loaded the runner or a Tasks API on the way.
from importlib.util import find_spec
assert find_spec("django_tasks_db") is None and find_spec("django_tasks") is None
loaded = [m for m in sys.modules if m.startswith(("django_extensions_admin.commands",
                                                  "django_tasks", "django.tasks"))]
assert not loaded, f"non-runner imports loaded task machinery: {loaded}"
# Adopting the runner is explicit, and without a backend it says so instead of running.
from django_extensions_admin import commands
commands.register("check", permission="auth.view_user")
from django.core import checks
errors = [m.id for m in checks.run_checks() if m.id.startswith("django_extensions_admin.")]
assert errors == ["django_extensions_admin.E101"], errors
for name in ("index", "launch", "result"):
    get_template(f"django_extensions_admin/commands/{name}.html")
assert finders.find("django_extensions_admin/commands.css")
# Branding is a template a project extends; unadopted, it renders nothing and checks nothing.
get_template("django_extensions_admin/branding/base_site.html")
assert finders.find("django_extensions_admin/branding.css"), "staticfiles cannot find it"
assert not [m for m in checks.run_checks() if m.id.startswith("django_extensions_admin.E2")]
print(f"import smoke OK: django_extensions_admin {pkg.__version__} from {root}")
PY
) | tee "$ART/smoke-install.txt"

# --------------------------------------------------------------------------
step "6/9 test matrix"
# Each lane installs exactly the line README documents for its Django version.
run_suite() {
  local env="$1" spec="$2" label="$3" tasks="$4"
  ensure_env "$env" "django==$spec" "$tasks"
  local version
  version="$("$VENVS/$env/bin/python" -c 'import django; print(django.get_version())')"
  echo "django ($env) $version" >> "$ART/versions.txt"
  echo "--- $label: Django $version ---"
  PYTHONPATH="$ROOT/src:$ROOT" "$VENVS/$env/bin/python" tests/runtests.py tests \
    > "$ART/tests-$env.txt" 2>&1 || { tail -40 "$ART/tests-$env.txt"; fail "$label suite failed"; }
  tail -3 "$ART/tests-$env.txt"
}
TASKS_DB="django-tasks-db==0.13.0"
run_suite dj52 "5.2.*" "Django 5.2 LTS" "django-tasks-db[compat]==0.13.0"
run_suite dj60 "6.0.*" "Django 6.0" "$TASKS_DB"
echo "tasks         $("$VENVS/dj60/bin/python" -c 'import importlib.metadata as m; print("django-tasks-db", m.version("django-tasks-db"))')" >> "$ART/versions.txt"

# --------------------------------------------------------------------------
step "7/9 real worker"
# The command runner end to end: the admin in the test process, a separately started
# db_worker process on a shared SQLite file, and a third process for pruning.
rm -rf "$ART/worker"
for env in dj52 dj60; do
  echo "--- worker journeys: $env ---"
  PYTHONPATH="$ROOT/src:$ROOT" DJANGO_SETTINGS_MODULE=worker_tests.settings \
    WORKER_ARTIFACTS="$ART/worker/$env" \
    "$VENVS/$env/bin/python" tests/runtests.py worker_tests \
    > "$ART/tests-worker-$env.txt" 2>&1 || { tail -40 "$ART/tests-worker-$env.txt"; fail "$env worker journeys failed"; }
  tail -3 "$ART/tests-worker-$env.txt"
done
if pgrep -f "django db_worker" >/dev/null; then
  pgrep -af "django db_worker"
  fail "a db_worker process outlived its test"
fi
rm -f "$ART"/worker/*/*.sqlite3

# --------------------------------------------------------------------------
step "8/9 browser smoke"
ensure_env browser "django==6.0.*" "$TASKS_DB" "playwright==1.63.0"
BROWSER_PY="$VENVS/browser/bin/python"
CHROMIUM=$("$BROWSER_PY" -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    print(p.chromium.executable_path)
" 2>/dev/null) || fail "playwright is not usable in $VENVS/browser"
if [ ! -x "$CHROMIUM" ]; then
  echo "chromium not in $PLAYWRIGHT_CACHE, downloading from the official host"
  "$VENVS/browser/bin/playwright" install chromium || fail "could not install chromium"
fi
echo "chromium      $CHROMIUM" >> "$ART/versions.txt"
echo "playwright    $("$BROWSER_PY" -c 'import importlib.metadata as m; print(m.version("playwright"))')" >> "$ART/versions.txt"

rm -f "$ART"/browser/*.png
PYTHONPATH="$ROOT/src:$ROOT" DJANGO_SETTINGS_MODULE=browser_tests.settings \
  ADMIN_EXTENSIONS_ARTIFACTS="$ART/browser" \
  "$BROWSER_PY" tests/runtests.py browser_tests \
  > "$ART/tests-browser.txt" 2>&1 || { tail -40 "$ART/tests-browser.txt"; fail "browser smoke failed"; }
tail -3 "$ART/tests-browser.txt"

SHOTS=$(find "$ART/browser" -name '*.png' | wc -l)
[ "$SHOTS" -ge 10 ] || fail "expected screenshots under artifacts/browser, found $SHOTS"
echo "$SHOTS screenshots in artifacts/browser"

# --------------------------------------------------------------------------
step "9/9 cleanup"
# The live server and its in-memory database belong to the test process and are gone
# with it. Nothing else is started here, so nothing else is killed: a demo server the
# user started stays up on purpose.
rm -f "$ROOT/demo/demo-verify.sqlite3"

printf '\nGATE PASSED\n'
cat "$ART/versions.txt"
