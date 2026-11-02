"""Writes more than the runner keeps, and markup that must stay text."""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Write a lot."

    def add_arguments(self, parser):
        parser.add_argument("--chars", type=int, default=100)

    def handle(self, *, chars, **options):
        self.stdout.write('<script>window.__pwned = 1</script><img src=x onerror="alert(1)">')
        self.stdout.write("x" * chars, ending="")
        self.stdout.write("THE-END")
