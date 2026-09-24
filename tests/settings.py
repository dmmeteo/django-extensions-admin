"""Settings for the django-extensions-admin test suite."""

from importlib.util import find_spec

# Django 6.0 has django.tasks; on 5.2 the same API comes from the django-tasks backport.
NATIVE_TASKS = find_spec("django.tasks") is not None
TASKS_PACKAGE = "django.tasks" if NATIVE_TASKS else "django_tasks"

SECRET_KEY = "admin-ext-tests-not-a-real-secret"
DEBUG = False
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django_extensions_admin",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_tasks_db",
    "tests.testapp",
]
if not NATIVE_TASKS:
    INSTALLED_APPS.insert(-2, "django_tasks")

MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "tests.urls"

TEMPLATES = [
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
]

DATABASES = {
    "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"},
    # A second database alias, only for the tests that prove ATOMIC_REQUESTS handling
    # covers every Django database and not just "default".
    "other": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"},
}

# No "default" alias on purpose: the runner must use the alias it is given, never
# Django's default (which is the inline ImmediateBackend). The other two are refused.
TASKS = {
    "commands": {"BACKEND": "django_tasks_db.DatabaseBackend"},
    "immediate": {"BACKEND": f"{TASKS_PACKAGE}.backends.immediate.ImmediateBackend"},
    "dummy": {"BACKEND": f"{TASKS_PACKAGE}.backends.dummy.DummyBackend"},
    "unreachable": {"BACKEND": "tests.testapp.task_backends.UnreachableBackend"},
}
ADMIN_EXTENSIONS = {"COMMANDS_TASK_BACKEND": "commands"}

STATIC_URL = "/static/"
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
