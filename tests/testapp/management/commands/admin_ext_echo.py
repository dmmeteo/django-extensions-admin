"""Harmless: prints its options and where it ran; --touch leaves a visible side effect."""

import os

from django.core.management.base import BaseCommand

from tests.testapp.models import Device


class Command(BaseCommand):
    help = "Echo a message a few times."

    def add_arguments(self, parser):
        parser.add_argument("--message", default="hello")
        parser.add_argument("--times", type=int, default=1)
        parser.add_argument("--touch", default="")
        parser.add_argument("--device", default=None)

    def handle(self, *, message, times, touch, device, **options):
        for _ in range(times):
            self.stdout.write(message)
        if device is not None:
            self.stdout.write(f"device={device.name}")
        if touch:
            Device.objects.create(name=touch)
        self.stdout.write(f"pid={os.getpid()}")
        self.stderr.write("done")
