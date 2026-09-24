"""Exits the way `makemigrations --check` does: output first, then sys.exit(code)."""

import sys

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Exit with a status code."

    def add_arguments(self, parser):
        parser.add_argument("--code", type=int, default=3)

    def handle(self, *, code, **options):
        self.stdout.write(f"about to exit with {code}")
        sys.exit(code)
