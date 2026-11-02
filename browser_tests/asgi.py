"""The ASGI server the panel and REPL journeys run against: the demo, plus static files."""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "browser_tests.settings")

# Importing the settings first puts demo/ on sys.path, as it does for the test process.
import browser_tests.settings  # noqa: F401, I001
from demoproject.asgi import application as demo_application
from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler

application = demo_application
application.application_mapping["http"] = ASGIStaticFilesHandler(
    application.application_mapping["http"]
)
