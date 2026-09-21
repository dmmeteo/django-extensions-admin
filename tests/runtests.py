#!/usr/bin/env python
"""Run the django-extensions-admin test suite. Usage: python tests/runtests.py [labels...]"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.settings")

import django
from django.conf import settings
from django.test.utils import get_runner


def main():
    django.setup()
    labels = sys.argv[1:] or ["tests"]
    runner_class = get_runner(settings)
    failures = runner_class(verbosity=2, interactive=False).run_tests(labels)
    sys.exit(bool(failures))


if __name__ == "__main__":
    main()
