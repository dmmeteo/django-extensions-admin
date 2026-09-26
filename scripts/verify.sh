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
# Every declared Python runs in some lane: 3.14 with Django 5.2 is the first known
# consumer, 3.12 is the lowest requires-python, 3.13 carries Django 6.0 and the browser.
PY_DEFAULT="3.13"
PY_SMOKE="3.14"

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
# ensure_env <name> <python> <requirement...> - build the venv only when either changed.
ensure_env() {
  local name="$1" python="$2"; shift 2
  local venv="$VENVS/$name"
  local stamp="$venv/.stamp"
  local want
  want="$(printf '%s\n' "py$python" "$@" | sort | md5sum | cut -d' ' -f1)"
  if [ -x "$venv/bin/python" ] && [ -f "$stamp" ] && [ "$(cat "$stamp")" = "$want" ]; then
    return 0
  fi
  rm -rf "$venv"
  uv venv --python "$python" "$venv" >/dev/null
  uv pip install --python "$venv/bin/python" --quiet "$@"
  echo "$want" > "$stamp"
}

# --------------------------------------------------------------------------
step "2/9 lint"
ensure_env tools "$PY_DEFAULT" "ruff==0.14.*" "twine==7.*"
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
step "4/9 build wheel and sdist"
# Both artifacts are what an upload would send, so both are checked and both are installed.
rm -rf "$ROOT/dist"
uv build --out-dir "$ROOT/dist" >"$ART/build.txt" 2>&1 || { cat "$ART/build.txt"; fail "build failed"; }
WHEEL=$(ls "$ROOT/dist"/*.whl)
SDIST=$(ls "$ROOT/dist"/*.tar.gz)
echo "wheel         $WHEEL" >> "$ART/versions.txt"
echo "sdist         $SDIST" >> "$ART/versions.txt"

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
# Only the package and its dist-info: no tests, spikes, demo, caches or bytecode.
stray = [
    n for n in names
    if not n.startswith(("django_extensions_admin/", "django_extensions_admin-"))
    or "__pycache__" in n or n.endswith(".pyc")
]
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
if stray:
    sys.stderr.write("unexpected files in wheel:\n" + "\n".join(stray) + "\n")
    raise SystemExit(1)
PY
[ $? -eq 0 ] || fail "wheel is missing static files or templates"
echo "wheel contains every template and static asset"

python3 - "$SDIST" "$WHEEL" >"$ART/sdist-contents.txt" <<'PY' || { cat "$ART/sdist-contents.txt"; fail "sdist contents are wrong"; }
import sys, tarfile, zipfile
with tarfile.open(sys.argv[1]) as sdist:
    names = [n.split("/", 1)[1] for n in sdist.getnames() if "/" in n and not sdist.getmember(n).isdir()]
print("\n".join(sorted(names)))
allowed = {"README.md", "ROADMAP.md", "LICENSE", "pyproject.toml", "PKG-INFO", ".gitignore"}
stray = [
    n for n in names
    if (n not in allowed and not n.startswith("src/django_extensions_admin/"))
    or "__pycache__" in n or n.endswith(".pyc")
]
# The sdist carries the same package files the wheel does.
wheel = {n for n in zipfile.ZipFile(sys.argv[2]).namelist() if n.startswith("django_extensions_admin/")}
missing = sorted(wheel - {n.removeprefix("src/") for n in names})
if stray or missing:
    sys.stderr.write(f"unexpected in sdist: {stray}\nmissing from sdist: {missing}\n")
    raise SystemExit(1)
PY
echo "sdist holds the package, README, ROADMAP, LICENSE and nothing else"

# PyPI renders README without the repository around it: a relative link would be dead there.
RELATIVE=$(grep -nE '\]\((\./)?[A-Za-z.][^):]*\)' README.md || true)
[ -z "$RELATIVE" ] || { echo "$RELATIVE"; fail "README has relative links that break on PyPI"; }
"$VENVS/tools/bin/twine" check --strict "$WHEEL" "$SDIST" 2>&1 | tee "$ART/twine-check.txt" \
  || fail "twine check rejected the artifacts (see artifacts/twine-check.txt)"
echo "twine         $("$VENVS/tools/bin/twine" --version | head -1)" >> "$ART/versions.txt"

# --------------------------------------------------------------------------
step "5/9 clean-install smoke"
: > "$ART/smoke-install.txt"
for ARTIFACT in "$WHEEL" "$SDIST"; do
  echo "--- $(basename "$ARTIFACT") on Python $PY_SMOKE ---" | tee -a "$ART/smoke-install.txt"
  rm -rf "$VENVS/smoke"
  uv venv --python "$PY_SMOKE" "$VENVS/smoke" >/dev/null
  uv pip install --python "$VENVS/smoke/bin/python" --quiet "$ARTIFACT"
  # Run from /tmp with no source on the path: this must import the installed artifact.
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
assert "site-packages" in str(root), f"imported from the source tree, not the artifact: {root}"
from importlib.metadata import version
assert version("django-extensions-admin") == pkg.__version__, version("django-extensions-admin")
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
print(f"import smoke OK: django_extensions_admin {pkg.__version__} on Python {sys.version.split()[0]} from {root}")
PY
  ) | tee -a "$ART/smoke-install.txt"
done

# --------------------------------------------------------------------------
step "6/9 test matrix"
# Each lane installs exactly the line README documents for its Django version.
run_suite() {
  local env="$1" python="$2" spec="$3" label="$4" tasks="$5"
  ensure_env "$env" "$python" "django==$spec" "$tasks"
  local version
  version="$("$VENVS/$env/bin/python" -c 'import django, platform; print(django.get_version(), "on Python", platform.python_version())')"
  echo "django ($env) $version" >> "$ART/versions.txt"
  echo "--- $label: Django $version ---"
  PYTHONPATH="$ROOT/src:$ROOT" "$VENVS/$env/bin/python" tests/runtests.py tests \
    > "$ART/tests-$env.txt" 2>&1 || { tail -40 "$ART/tests-$env.txt"; fail "$label suite failed"; }
  tail -3 "$ART/tests-$env.txt"
}
TASKS_DB="django-tasks-db==0.13.0"
TASKS_COMPAT="django-tasks-db[compat]==0.13.0"
LANES="dj52py314 dj52py312 dj60py313"
run_suite dj52py314 3.14 "5.2.*" "Django 5.2 LTS, first consumer" "$TASKS_COMPAT"
run_suite dj52py312 3.12 "5.2.*" "Django 5.2 LTS, lowest Python" "$TASKS_COMPAT"
run_suite dj60py313 3.13 "6.0.*" "Django 6.0" "$TASKS_DB"
echo "tasks         $("$VENVS/dj60py313/bin/python" -c 'import importlib.metadata as m; print("django-tasks-db", m.version("django-tasks-db"))')" >> "$ART/versions.txt"

# --------------------------------------------------------------------------
step "7/9 real worker"
# The command runner end to end: the admin in the test process, a separately started
# db_worker process on a shared SQLite file, and a third process for pruning.
rm -rf "$ART/worker"
for env in $LANES; do
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
ensure_env browser "$PY_DEFAULT" "django==6.0.*" "$TASKS_DB" "playwright==1.63.0"
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
