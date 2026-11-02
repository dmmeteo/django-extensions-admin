"""Probe one installed selection of features from outside the source tree.

    python isolation.py <dist-dir> <feature,...|bare>

Run with -I from a directory with no source in it. It proves which distributions and files
are installed (and that they are byte-for-byte the gate's own wheels), that every selected
feature works on a configured Django project, that no unselected feature has a module,
file or third-party dependency on disk, and that a missing feature fails with its extra.
"""

import base64
import csv
import hashlib
import io
import json
import sys
import tempfile
import zipfile
from importlib import metadata
from importlib.util import find_spec
from pathlib import Path

FEATURES = (
    "buttons",
    "jsonwidget",
    "filters",
    "commands",
    "branding",
    "environment",
    "panel",
    "repl",
)
# What each feature brings beyond Django and the core; nothing else may appear.
THIRD_PARTY = {"repl": {"channels"}}
APPS = ("environment", "panel", "repl")

dist_dir = Path(sys.argv[1])
wanted = set() if sys.argv[2] == "bare" else set(sys.argv[2].split(","))
if "repl" in wanted:
    wanted.add("panel")
absent = set(FEATURES) - wanted
here = Path.cwd()
report = {"selection": sorted(wanted), "cwd": str(here)}

assert not any(
    p for p in sys.path if p and Path(p).resolve() == Path(__file__).resolve().parents[2]
), sys.path
import django_extensions_admin as core  # noqa: E402

root = Path(core.__file__).parent
assert "site-packages" in root.parts, f"imported from {root}, not an installed artifact"
report["package_dir"] = str(root)


def wheel_record(name):
    wheel = next(dist_dir.glob(name.replace("-", "_") + "-*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        record = next(n for n in archive.namelist() if n.endswith(".dist-info/RECORD"))
        rows = csv.reader(io.StringIO(archive.read(record).decode()))
        return {path: digest for path, digest, _ in rows if digest and ".dist-info/" not in path}


def installed_record(dist):
    rows = csv.reader(io.StringIO(dist.read_text("RECORD")))
    return {path: digest for path, digest, _ in rows if digest and ".dist-info/" not in path}


distributions = {d.metadata["Name"].lower(): d for d in metadata.distributions()}
ours = {name for name in distributions if name.startswith("django-extensions-admin")}
expected = {"django-extensions-admin"} | {f"django-extensions-admin-{f}" for f in wanted}
assert ours == expected, f"installed {sorted(ours)}, expected {sorted(expected)}"
for name in sorted(ours):
    dist = distributions[name]
    record = installed_record(dist)
    assert record == wheel_record(name), f"{name} on disk is not the gate's wheel"
    for path, digest in record.items():
        data = (Path(dist.locate_file(path))).read_bytes()
        actual = (
            "sha256="
            + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        )
        assert actual == digest, f"{path} was modified after install"
report["distributions"] = sorted(ours)

on_disk = sorted(
    str(p.relative_to(root))
    for p in root.rglob("*")
    if p.is_file() and "__pycache__" not in p.parts
)
report["files"] = len(on_disk)
for feature in absent:
    assert find_spec(f"django_extensions_admin.{feature}") is None, f"{feature} is importable"
    leftovers = [
        p for p in wheel_record(f"django-extensions-admin-{feature}") if (root.parent / p).exists()
    ]
    assert not leftovers, f"{feature} left files: {leftovers}"
    for dependency in THIRD_PARTY.get(feature, ()):
        assert find_spec(dependency) is None, f"{dependency} is installed without {feature}"
for feature in wanted:
    assert find_spec(f"django_extensions_admin.{feature}") is not None, f"{feature} missing"
    for dependency in THIRD_PARTY.get(feature, ()):
        assert find_spec(dependency) is not None, f"{dependency} missing for {feature}"
# Nothing third-party at all beyond Django, asgiref, sqlparse and the selected features' own.
allowed = {"django", "asgiref", "sqlparse", "tzdata", "pip", "setuptools", *ours}
for feature in wanted:
    allowed |= THIRD_PARTY.get(feature, set())
extra = sorted(set(distributions) - allowed)
assert not extra, f"unexpected distributions: {extra}"

# A name from a feature that is not installed says which extra provides it.
for name, feature in core.EXPORTS.items():
    if feature in absent:
        try:
            getattr(core, name)
        except ImportError as error:
            assert f"django-extensions-admin[{feature}]" in str(error), error
        else:
            raise AssertionError(f"{name} resolved without {feature}")

import django  # noqa: E402
from django.conf import settings  # noqa: E402

state = Path(tempfile.mkdtemp())
apps = ["django_extensions_admin", *[f"django_extensions_admin.{f}" for f in APPS if f in wanted]]
configured = {"ENVIRONMENT": "Isolation"} if "environment" in wanted else {}
if "repl" in wanted:
    configured |= {"REPL_ENABLED": True, "REPL_LOCK_PATH": str(state / "repl.lock")}
settings.configure(
    DEBUG=False,
    SECRET_KEY="isolation-probe",  # noqa: S106 - a throwaway probe project
    ALLOWED_HOSTS=["testserver"],
    INSTALLED_APPS=[
        *apps,
        "django.contrib.admin",
        "django.contrib.auth",
        "django.contrib.contenttypes",
        "django.contrib.messages",
        "django.contrib.sessions",
        "django.contrib.staticfiles",
    ],
    MIDDLEWARE=[
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
    ],
    ROOT_URLCONF="isolation_urls",
    DATABASES={
        "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": str(state / "db.sqlite3")}
    },
    STATIC_URL="/static/",
    TEMPLATES=[
        {
            "BACKEND": "django.template.backends.django.DjangoTemplates",
            "APP_DIRS": True,
            "OPTIONS": {
                "context_processors": [
                    "django.template.context_processors.request",
                    "django.contrib.auth.context_processors.auth",
                    "django.contrib.messages.context_processors.messages",
                ]
            },
        }
    ],
    ADMIN_EXTENSIONS=configured,
    USE_TZ=True,
    DEFAULT_AUTO_FIELD="django.db.models.AutoField",
)
(state / "isolation_urls.py").write_text(
    "from django.contrib import admin\nfrom django.urls import include, path\nurlpatterns = [\n"
    + (
        '    path("admin/repl/", include("django_extensions_admin.repl.urls")),\n'
        if "repl" in wanted
        else ""
    )
    + '    path("admin/", admin.site.urls),\n]\n'
)
sys.path.append(str(state))
django.setup()

from django.core import checks  # noqa: E402
from django.core.management import call_command  # noqa: E402

messages = [m for m in checks.run_checks() if m.level >= checks.WARNING]
assert not messages, [str(m) for m in messages]
call_command("migrate", verbosity=0)

# A star import works on any selection and brings exactly the installed features' names.
namespace = {}
exec("from django_extensions_admin import *", namespace)  # noqa: S102 - a fixed statement
star = sorted(n for n in namespace if not n.startswith("__"))
assert star == sorted(n for n, f in core.EXPORTS.items() if f in wanted), star
report["star_import"] = star

from django.contrib.auth.models import User  # noqa: E402
from django.contrib.staticfiles import finders  # noqa: E402
from django.template.loader import get_template  # noqa: E402
from django.test import Client  # noqa: E402

root_user = User.objects.create_superuser("root", "root@example.invalid", "pw")
client = Client()
client.force_login(root_user)
page = client.get("/admin/").content.decode()
assert ("admin-ext-environment" in page) == ("environment" in wanted), "environment indicator"
assert ("admin-ext-panel" in page) == ("repl" in wanted), "tools panel"

probes = {
    "buttons": lambda: (
        core.ButtonsMixin,
        get_template("django_extensions_admin/buttons/confirm.html"),
        finders.find("django_extensions_admin/buttons.css"),
    ),
    "jsonwidget": lambda: (
        "admin-ext-json-key" in core.render_json({"n": 1}),
        finders.find("django_extensions_admin/json-widget.js"),
    ),
    "filters": lambda: (
        core.DateRangeFilter.template,
        get_template("django_extensions_admin/filters/choice.html"),
        finders.find("django_extensions_admin/choice-filters.js"),
    ),
    "commands": lambda: (
        __import__("django_extensions_admin.commands", fromlist=["register"]).register,
        get_template("django_extensions_admin/commands/launch.html"),
    ),
    "branding": lambda: (
        get_template("django_extensions_admin/branding/base_site.html"),
        finders.find("django_extensions_admin/branding.css"),
    ),
    "environment": lambda: (
        finders.find("django_extensions_admin/environment/environment.css"),
        ">Isolation</span>" in page,
    ),
    "panel": lambda: (finders.find("django_extensions_admin/panel/panel.js"),),
    "repl": lambda: (
        finders.find("django_extensions_admin/repl/vendor/ghostty-web/ghostty-vt.wasm"),
        client.get("/admin/repl/state/").json()["session"] is None,
    ),
}
# Every other feature runs first, and none of them may load the runner or a Tasks API on the way.
TASK_MACHINERY = ("django_extensions_admin.commands", "django_tasks", "django.tasks")
for feature in sorted(wanted - {"commands"}):
    results = probes[feature]()
    assert all(results), f"{feature} probe failed: {results}"
loaded = [m for m in sys.modules if m.startswith(TASK_MACHINERY)]
assert not loaded, f"non-runner features loaded task machinery: {loaded}"
report["task_machinery_loaded_by_other_features"] = loaded
if "commands" in wanted:
    assert all(probes["commands"]())
    # Adopting the runner is explicit, and without a backend it says so instead of running.
    from django_extensions_admin import commands

    commands.register("check", permission="auth.view_user")
    errors = [m.id for m in checks.run_checks() if m.id.startswith("django_extensions_admin.")]
    assert errors == ["django_extensions_admin.E101"], errors
report["checks"] = "no warnings"

# A shared settings file that configures every feature degrades: each absent feature's
# setting is a warning naming its extra, never an error or a crash.
from django.test.utils import override_settings  # noqa: E402

from django_extensions_admin.apps import check_feature_settings  # noqa: E402

everything = {
    "JSON_WIDGET_DEFAULT": True,
    "COMMANDS_TASK_BACKEND": "commands",
    "BRANDING": {"COLORS": {"accent": "#ffcc00"}},
    "ENVIRONMENT": "Probe",
    "PANEL_SIDE": "left",
    "REPL_ENABLED": True,
}
owner = {
    "JSON_WIDGET_DEFAULT": "jsonwidget",
    "COMMANDS_TASK_BACKEND": "commands",
    "BRANDING": "branding",
    "ENVIRONMENT": "environment",
    "PANEL_SIDE": "panel",
    "REPL_ENABLED": "repl",
}
with override_settings(ADMIN_EXTENSIONS=everything):
    warned = sorted(
        w.obj for w in check_feature_settings() if w.id == "django_extensions_admin.W001"
    )
    expected = sorted(f"ADMIN_EXTENSIONS[{k!r}]" for k, f in owner.items() if f in absent)
    assert warned == expected, (warned, expected)
    # Only an installed commands feature may report its own error here (no Tasks backend).
    errors = [m.id for m in checks.run_checks() if m.level >= checks.ERROR]
    assert set(errors) <= {"django_extensions_admin.E101"}, errors
report["absent_feature_settings"] = f"{len(warned)} W001 warnings, no errors"
print(json.dumps(report))
