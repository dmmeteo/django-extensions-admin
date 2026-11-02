"""Prints a little, then fails the way a management command should."""

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Fail on purpose."

    def add_arguments(self, parser):
        parser.add_argument("--padding", type=int, default=0)

    def handle(self, *, padding, **options):
        self.stdout.write("partial output before the failure")
        raise CommandError("deliberate <b>failure</b>" + "!" * padding)
