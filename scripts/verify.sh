#!/usr/bin/env bash
# Deterministic gate for django-extensions-admin and its feature distributions.
#
#   bash scripts/verify.sh
#
# Every stage is required. A missing tool, a missing acceptance test or any failure
# exits non-zero; nothing is skipped silently. Environments are cached by a hash of
# their requirements, so a second run is bounded. Every test runs against the built
# wheels, never against the source tree on PYTHONPATH.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ART="$ROOT/artifacts"
VENVS="$ROOT/.venvs"
DIST="$ROOT/dist"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$ROOT/.uvcache}"
export PYTHONDONTWRITEBYTECODE=1
# Every declared Python runs in some lane: 3.14 with Django 5.2 is the first known
# consumer, 3.12 is the lowest requires-python, 3.13 carries Django 6.0 and the browser.
PY_DEFAULT="3.13"
PY_SMOKE="3.14"
VERSION="0.1.0"
# The core distribution and every feature distribution, each with its own source root.
FEATURES="buttons jsonwidget filters commands branding environment panel repl"
# Pins for the optional dependencies the tests exercise. Not runtime dependencies of the core.
CHANNELS="channels==4.3.2"
DAPHNE="daphne==4.2.3"
IPYTHON="ipython==9.17.1"
DJANGO_EXTENSIONS="django-extensions==4.1"

mkdir -p "$ART" "$ART/browser"

step() { printf '\n=== %s ===\n' "$1"; }
fail() { printf '\nGATE FAILED: %s\n' "$1" >&2; exit 1; }

# --------------------------------------------------------------------------
step "1/11 preflight"
command -v uv  >/dev/null || fail "uv is required (https://docs.astral.sh/uv/)"
command -v node >/dev/null || fail "node is required for the JavaScript syntax check"
command -v python3 >/dev/null || fail "python3 is required for the artifact checks"

PLAYWRIGHT_CACHE="${PLAYWRIGHT_BROWSERS_PATH:-$HOME/.cache/ms-playwright}"

{
  echo "date          $(date -Is)"
  echo "uname         $(uname -sr)"
  echo "uv            $(uv --version)"
  echo "node          $(node --version)"
  echo "revision      $(git rev-parse HEAD 2>/dev/null || echo 'not a git checkout')"
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

# Every build reuses the file names django_extensions_admin*-0.1.0-*, so uv's cache could hand
# back an earlier build's copy: our own distributions are always refreshed. (The isolation probe
# compares every installed file with this run's wheels and caught exactly that.)
OURS_REFRESH="--refresh-package django-extensions-admin $(for f in $FEATURES; do printf -- '--refresh-package django-extensions-admin-%s ' "$f"; done)"

# install_wheels <venv> - this run's nine wheels, replacing whatever an earlier run left.
install_wheels() {
  uv pip install --python "$VENVS/$1/bin/python" --quiet --no-deps --reinstall $OURS_REFRESH "$DIST"/*.whl
}

# --------------------------------------------------------------------------
step "2/11 lint"
ensure_env tools "$PY_DEFAULT" "ruff==0.14.*" "twine==7.*" "ty==0.0.95"
"$VENVS/tools/bin/ruff" check . 2>&1 | tee "$ART/lint-ruff-check.txt"
"$VENVS/tools/bin/ruff" format --check . 2>&1 | tee "$ART/lint-ruff-format.txt"
echo "ruff          $("$VENVS/tools/bin/ruff" --version)" >> "$ART/versions.txt"

# Our own scripts only; the vendored terminal is checked by its published integrity instead.
JS_FILES=$(find src packages -name '*.js' -not -path '*/vendor/*' | sort)
[ -n "$JS_FILES" ] || fail "no JavaScript assets found to check"
for js in $JS_FILES; do
  node --check "$js" || fail "syntax error in $js"
  echo "node --check OK $js"
done | tee "$ART/lint-js.txt"

# --------------------------------------------------------------------------
step "3/11 naming check"
# The distribution was renamed; no identifier from an earlier working name may survive.
# --exclude: this script carries the pattern itself and would match on every run.
LEFTOVERS=$(grep -rniE 'admin[-_]kit|adminkit|jsonkit|django_admin_repl|django-admin-repl' \
    --include='*.py' --include='*.html' --include='*.css' --include='*.js' \
    --include='*.toml' --include='*.md' --include='*.sh' --exclude='verify.sh' \
    --exclude-dir=vendor \
    src packages tests browser_tests demo scripts README.md ROADMAP.md pyproject.toml 2>/dev/null || true)
if [ -n "$LEFTOVERS" ]; then
  echo "$LEFTOVERS" | tee "$ART/naming.txt"
  fail "stale name found (see artifacts/naming.txt)"
fi
test -d src/django_extensions_admin || fail "package directory src/django_extensions_admin is missing"
grep -q '^name = "django-extensions-admin"' pyproject.toml || fail "distribution name is wrong"
for feature in $FEATURES; do
  grep -q "^name = \"django-extensions-admin-$feature\"" "packages/$feature/pyproject.toml" \
    || fail "packages/$feature does not build django-extensions-admin-$feature"
done
echo "no stale identifiers; core django-extensions-admin and $(echo $FEATURES | wc -w) feature distributions" \
  | tee "$ART/naming.txt"

# --------------------------------------------------------------------------
step "4/11 build every wheel and sdist"
# uv builds each sdist first and the wheel from that sdist, so a wheel proves its sdist builds.
rm -rf "$DIST"
: > "$ART/build.txt"
for project in . $(for f in $FEATURES; do echo "packages/$f"; done); do
  uv build --out-dir "$DIST" "$project" >>"$ART/build.txt" 2>&1 || { cat "$ART/build.txt"; fail "build of $project failed"; }
done
ls -1 "$DIST" | tee "$ART/dist-files.txt"
[ "$(ls "$DIST"/*.whl | wc -l)" -eq 9 ] && [ "$(ls "$DIST"/*.tar.gz | wc -l)" -eq 9 ] \
  || fail "expected nine wheels and nine sdists"

python3 - "$ROOT" "$DIST" "$VERSION" $FEATURES >"$ART/dist-contents.txt" 2>&1 <<'PY' || { cat "$ART/dist-contents.txt"; fail "a distribution's contents or metadata are wrong"; }
import re, sys, tarfile, tomllib, zipfile
from pathlib import Path

root, dist, version, features = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3], sys.argv[4:]
core_version = re.search(r'__version__ = "([^"]+)"', (root / "src/django_extensions_admin/__init__.py").read_text())[1]
assert core_version == version, (core_version, version)
license_text = (root / "LICENSE").read_text()
problems = []

def files_under(base):
    return sorted(
        str(p.relative_to(base)) for p in base.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and not p.name.endswith(".pyc")
    )

projects = {"django-extensions-admin": root} | {f"django-extensions-admin-{f}": root / "packages" / f for f in features}
for name, project in projects.items():
    meta = tomllib.loads((project / "pyproject.toml").read_text())["project"]
    stem = name.replace("-", "_")
    wheel = dist / f"{stem}-{version}-py3-none-any.whl"
    sdist = dist / f"{stem}-{version}.tar.gz"
    expected = files_under(project / "src")
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        payload = sorted(n for n in names if ".dist-info/" not in n)
        metadata = archive.read(next(n for n in names if n.endswith(".dist-info/METADATA"))).decode()
    print(f"--- {wheel.name}: {len(payload)} files")
    print("\n".join(payload))
    if payload != expected:
        problems.append(f"{wheel.name}: missing {sorted(set(expected) - set(payload))}, stray {sorted(set(payload) - set(expected))}")
    requires = sorted(line.split(":", 1)[1].strip() for line in metadata.splitlines() if line.startswith("Requires-Dist:"))
    print("Requires-Dist:", requires)
    if name == "django-extensions-admin":
        base = [r for r in requires if "extra ==" not in r]
        if base not in (["Django<7,>=5.2"], ["django<7,>=5.2"]):
            problems.append(f"core depends on more than Django: {base}")
        extras = sorted(line.split(":", 1)[1].strip() for line in metadata.splitlines() if line.startswith("Provides-Extra:"))
        if extras != sorted([*[f for f in features if f != "panel"], "all"]):
            problems.append(f"core extras are {extras}")
        for r in requires:
            if "extra ==" in r and not re.fullmatch(rf"django-extensions-admin-[a-z]+=={re.escape(version)}; extra == '[a-z]+'", r):
                problems.append(f"core extra is not an exact pin on a feature distribution: {r}")
    else:
        pins = [r for r in requires if r.startswith("django-extensions-admin")]
        if not pins or any(not r.endswith(f"=={version}") for r in pins):
            problems.append(f"{name} must pin its siblings to =={version}: {pins}")
        others = sorted(r for r in requires if not r.startswith("django-extensions-admin"))
        allowed = {"django-extensions-admin-repl": ["channels>=4.1"]}.get(name, [])
        if others != allowed:
            problems.append(f"{name} brings {others}, expected {allowed}")
        if (project / "LICENSE").read_text() != license_text:
            problems.append(f"{name} LICENSE differs from the repository's")
        if meta["version"] != version:
            problems.append(f"{name} version {meta['version']}")
        if (project / "src/django_extensions_admin/__init__.py").exists():
            problems.append(f"{name} would overwrite the core's __init__.py")
    with tarfile.open(sdist) as archive:
        members = sorted(m.name.split("/", 1)[1] for m in archive.getmembers() if m.isfile())
    allowed_top = {"README.md", "LICENSE", "pyproject.toml", "PKG-INFO", ".gitignore"} | ({"ROADMAP.md"} if project == root else set())
    stray = [m for m in members if m not in allowed_top and not m.startswith("src/django_extensions_admin/")]
    missing = sorted({f"src/{p}" for p in expected} - set(members))
    if stray or missing or any("__pycache__" in m or m.endswith(".pyc") for m in members):
        problems.append(f"{sdist.name}: stray {stray}, missing {missing}")
    # PyPI renders each README without the repository around it: relative links would be dead.
    readme = (project / "README.md").read_text()
    relative = re.findall(r"\]\((?:\./)?[A-Za-z.][^):]*\)", readme)
    if relative:
        problems.append(f"{name} README has relative links: {relative}")

# No two distributions may ship the same file: pip would let one overwrite or remove the other's.
owners = {}
for project in projects.values():
    for path in files_under(project / "src"):
        if path in owners:
            problems.append(f"{path} is shipped by both {owners[path]} and {project.name}")
        owners[path] = project.name
if problems:
    sys.stderr.write("\n".join(problems) + "\n")
    raise SystemExit(1)
print(f"OK: nine distributions, each exactly its own source root, {len(owners)} files with one owner each")
PY
tail -1 "$ART/dist-contents.txt"
"$VENVS/tools/bin/twine" check --strict "$DIST"/* 2>&1 | tee "$ART/twine-check.txt" \
  || fail "twine check rejected the artifacts (see artifacts/twine-check.txt)"
echo "twine         $("$VENVS/tools/bin/twine" --version | head -1)" >> "$ART/versions.txt"
# The vendored terminal must be the published npm release, byte for byte.
(cd packages/repl/src/django_extensions_admin/repl/static/django_extensions_admin/repl/vendor/ghostty-web \
  && sha256sum -c "$ROOT/scripts/ci/ghostty-web.sha256") | tee "$ART/vendor-check.txt" \
  || fail "the vendored ghostty-web files changed"

# --------------------------------------------------------------------------
step "5/11 isolated installs"
# Each selection installs through the public extras into a fresh venv: Django (and Channels for
# the REPL) from PyPI first, then our distributions with --no-index from dist/ only, so an
# unpublished name can never resolve to someone else's upload. The probe runs with python -I
# from an empty directory: no source tree, no PYTHONPATH, no user site.
: > "$ART/isolation.txt"
PROBE_DIR="$(mktemp -d)"
probe() {
  local label="$1" venv="$2" selection="$3"
  (cd "$PROBE_DIR" && env -u PYTHONPATH "$venv/bin/python" -I "$ROOT/scripts/ci/isolation.py" "$DIST" "$selection") \
    > "$ART/isolation-$label.json" 2>&1 || { cat "$ART/isolation-$label.json"; fail "isolation probe $label failed"; }
  echo "$label: $(cat "$ART/isolation-$label.json")" | tee -a "$ART/isolation.txt"
}
lane() {
  local label="$1" spec="$2" selection="$3" venv="$VENVS/iso-$1"
  rm -rf "$venv"
  uv venv --python "$PY_SMOKE" "$venv" >/dev/null
  uv pip install --python "$venv/bin/python" --quiet "Django>=5.2,<7" \
    $(case "$selection" in *repl*) echo "channels>=4.1";; esac)
  uv pip install --python "$venv/bin/python" --quiet $OURS_REFRESH --no-index --find-links "$DIST" "$spec"
  probe "$label" "$venv" "$selection"
}
lane bare "django-extensions-admin==$VERSION" bare
# Every extra on its own, then a combination.
for extra in buttons jsonwidget filters commands branding environment repl; do
  lane "$extra" "django-extensions-admin[$extra]==$VERSION" "$extra"
done
lane buttons-repl "django-extensions-admin[buttons,repl]==$VERSION" buttons,repl
lane all "django-extensions-admin[all]==$VERSION" buttons,jsonwidget,filters,commands,branding,environment,repl
# Later: add a feature to the buttons+repl project, then remove one; the others keep every file.
venv="$VENVS/iso-buttons-repl"
uv pip install --python "$venv/bin/python" --quiet $OURS_REFRESH --no-index --find-links "$DIST" \
  "django-extensions-admin[buttons,repl,environment]==$VERSION"
probe add-environment "$venv" buttons,repl,environment
uv pip uninstall --python "$venv/bin/python" --quiet django-extensions-admin-buttons
probe remove-buttons "$venv" repl,environment
uv pip uninstall --python "$venv/bin/python" --quiet django-extensions-admin-repl django-extensions-admin-panel channels
probe remove-repl "$venv" environment
# The sdists are what an upload sends too: each one builds its own wheel (in an isolated build
# environment, so the build backend never enters the probed venv), and those wheels install and
# match the gate's wheels file for file.
SDIST_WHEELS="$VENVS/sdist-wheels"
rm -rf "$SDIST_WHEELS" "$VENVS/iso-sdist"
for sdist in "$DIST"/*.tar.gz; do
  uv build --quiet --wheel --out-dir "$SDIST_WHEELS" "$sdist" || fail "$(basename "$sdist") did not build a wheel"
done
uv venv --python "$PY_SMOKE" "$VENVS/iso-sdist" >/dev/null
uv pip install --python "$VENVS/iso-sdist/bin/python" --quiet "Django>=5.2,<7" "channels>=4.1"
uv pip install --python "$VENVS/iso-sdist/bin/python" --quiet $OURS_REFRESH --no-index \
  --find-links "$SDIST_WHEELS" "django-extensions-admin[all]==$VERSION"
probe sdist-all "$VENVS/iso-sdist" buttons,jsonwidget,filters,commands,branding,environment,repl
rm -rf "$PROBE_DIR"
echo "isolated installs: bare, each extra alone, buttons+repl, all, add and remove, sdists" | tee -a "$ART/isolation.txt"
# README "Quickstart" with ordinary pip, then a new project adopting [buttons,repl], a login, a
# REPL session and a server restart.
bash scripts/ci/quickstart.sh "$(uv python find "$PY_SMOKE")" "$ART" > "$ART/quickstart.txt" 2>&1 \
  || { tail -40 "$ART/quickstart.txt"; fail "the README quickstart failed"; }
tail -1 "$ART/quickstart.txt"

# --------------------------------------------------------------------------
step "6/11 test matrix"
# Each lane installs the backend line docs/commands.md documents for its Django version, the REPL's
# optional backends where noted, and then this run's wheels. The tests import the package
# from site-packages: PYTHONPATH holds only the repository root for tests/ and demo/.
run_suite() {
  local env="$1" python="$2" spec="$3" label="$4"; shift 4
  # channels.testing (the WebSocket tests) imports daphne, so every lane has both.
  ensure_env "$env" "$python" "django==$spec" "$CHANNELS" "$DAPHNE" "$@"
  install_wheels "$env"
  local version
  version="$("$VENVS/$env/bin/python" -c 'import django, platform; print(django.get_version(), "on Python", platform.python_version())')"
  echo "django ($env) $version" >> "$ART/versions.txt"
  echo "--- $label: Django $version ---"
  PYTHONPATH="$ROOT" "$VENVS/$env/bin/python" tests/runtests.py tests \
    > "$ART/tests-$env.txt" 2>&1 || { tail -60 "$ART/tests-$env.txt"; fail "$label suite failed"; }
  tail -3 "$ART/tests-$env.txt"
  grep -E "skipped '" "$ART/tests-$env.txt" | sed "s/^/  skipped in $env: /" || true
}
TASKS_DB="django-tasks-db==0.13.0"
TASKS_COMPAT="django-tasks-db[compat]==0.13.0"
LANES="dj52py314 dj52py312 dj60py313"
run_suite dj52py314 3.14 "5.2.*" "Django 5.2 LTS, first consumer" "$TASKS_COMPAT"
run_suite dj52py312 3.12 "5.2.*" "Django 5.2 LTS, lowest Python" "$TASKS_COMPAT" "$IPYTHON"
run_suite dj60py313 3.13 "6.0.*" "Django 6.0, IPython and shell_plus" "$TASKS_DB" "$IPYTHON" "$DJANGO_EXTENSIONS"
echo "tasks         $("$VENVS/dj60py313/bin/python" -c 'import importlib.metadata as m; print("django-tasks-db", m.version("django-tasks-db"))')" >> "$ART/versions.txt"
if pgrep -f "django_extensions_admin.repl.pty_child" >/dev/null; then
  pgrep -af "django_extensions_admin.repl.pty_child"
  fail "a REPL process outlived its test"
fi

# --------------------------------------------------------------------------
step "7/11 real worker"
# The command runner end to end: the admin in the test process, a separately started
# db_worker process on a shared SQLite file, and a third process for pruning.
rm -rf "$ART/worker"
for env in $LANES; do
  echo "--- worker journeys: $env ---"
  PYTHONPATH="$ROOT" DJANGO_SETTINGS_MODULE=worker_tests.settings \
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
step "8/11 browser smoke"
ensure_env browser "$PY_DEFAULT" "django==6.0.*" "$TASKS_DB" "playwright==1.63.0" "$CHANNELS" "$DAPHNE" "$IPYTHON"
install_wheels browser
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

rm -rf "$ART"/browser/*.png "$ART/browser-db"
PYTHONPATH="$ROOT" DJANGO_SETTINGS_MODULE=browser_tests.settings \
  ADMIN_EXTENSIONS_ARTIFACTS="$ART/browser" \
  "$BROWSER_PY" tests/runtests.py browser_tests \
  > "$ART/tests-browser.txt" 2>&1 || { tail -60 "$ART/tests-browser.txt"; fail "browser smoke failed"; }
tail -3 "$ART/tests-browser.txt"
grep -E "skipped '" "$ART/tests-browser.txt" | sed "s/^/  skipped in browser: /" || true

SHOTS=$(find "$ART/browser" -name '*.png' | wc -l)
[ "$SHOTS" -ge 20 ] || fail "expected screenshots under artifacts/browser, found $SHOTS"
echo "$SHOTS screenshots in artifacts/browser"
if pgrep -f "django_extensions_admin.repl.pty_child|daphne .*browser_tests" >/dev/null; then
  pgrep -af "django_extensions_admin.repl.pty_child|daphne .*browser_tests"
  fail "a REPL or ASGI server process outlived the browser journeys"
fi

# --------------------------------------------------------------------------
step "9/11 type report (not gating)"
# ty is pre-release: its findings are reported against real Django and channels sources and
# reviewed, not enforced. The count goes into the artifacts so a change in it is visible.
"$VENVS/tools/bin/ty" check --python "$VENVS/dj60py313" --output-format concise --exit-zero \
  src $(for f in $FEATURES; do echo "packages/$f/src"; done) > "$ART/ty-report.txt" 2>&1 || true
echo "ty $("$VENVS/tools/bin/ty" --version): $(grep -cE '^(error|warning)|: (error|warning)\[' "$ART/ty-report.txt" || true) diagnostics, see artifacts/ty-report.txt" \
  | tee -a "$ART/versions.txt"

# --------------------------------------------------------------------------
step "10/11 media provenance"
# The README's GIF and the REPL page's screenshot were captured from the UI files listed in the
# manifest. If any of those files changed since, the media show a UI that no longer exists:
# capture again.
python3 scripts/ci/media_check.py "$ROOT" | tee "$ART/media-check.txt" || fail "docs/media is stale or invalid"

# --------------------------------------------------------------------------
step "11/11 cleanup"
# The live servers and their databases belong to the test processes and are gone with them.
# A demo server the user started stays up on purpose.
rm -f "$ROOT/demo/demo-verify.sqlite3"

printf '\nGATE PASSED\n'
cat "$ART/versions.txt"
