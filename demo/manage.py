#!/usr/bin/env python
"""Disposable demo project for django-extensions-admin. Local use only."""

import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
# The package itself comes from the installed wheels (scripts/demo.sh builds them).
sys.path.insert(0, BASE)


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "demoproject.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
