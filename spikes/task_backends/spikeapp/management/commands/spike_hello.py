from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Harmless command for the task-backend spike: prints a greeting."

    def add_arguments(self, parser):
        parser.add_argument("--name", default="world")

    def handle(self, *args, name, **options):
        self.stdout.write(f"hello, {name}")
