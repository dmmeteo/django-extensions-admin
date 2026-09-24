"""Prints exactly what it was given, so a test can tell a passed value from a default."""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Report the options received."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--label", default="untitled")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--kinds", nargs="*", default=["all"])
        parser.add_argument("--devices", default=None)
        parser.add_argument("--when", default=None)

    def handle(self, *, limit, label, dry_run, kinds, devices, when, **options):
        self.stdout.write(f"limit={limit!r}")
        self.stdout.write(f"label={label!r}")
        self.stdout.write(f"dry_run={dry_run!r}")
        self.stdout.write(f"kinds={list(kinds)!r}")
        names = None if devices is None else sorted(device.name for device in devices)
        self.stdout.write(f"devices={names!r}")
        self.stdout.write(f"when={when.isoformat() if when else None!r}")
