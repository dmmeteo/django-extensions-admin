"""A command that would prompt unless it is told not to: the runner must say --noinput."""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Ask before doing anything."

    def add_arguments(self, parser):
        parser.add_argument("--noinput", "--no-input", action="store_false", dest="interactive")

    def handle(self, *, interactive, **options):
        if interactive:
            input("Are you sure? ")
        self.stdout.write(f"interactive={interactive}")
