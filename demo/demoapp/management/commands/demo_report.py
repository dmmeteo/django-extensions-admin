"""A harmless operational command for the demo: counts devices, optionally lists them."""

from django.core.management.base import BaseCommand

from demoapp.models import Device


class Command(BaseCommand):
    help = "Count devices per region. Reads only; changes nothing."

    def add_arguments(self, parser):
        parser.add_argument("--region", default="", help="Only this region.")
        parser.add_argument("--list", action="store_true", dest="list_devices")
        parser.add_argument("--note", default="", help="Printed verbatim at the top.")

    def handle(self, *, region, list_devices, note, **options):
        if note:
            self.stdout.write(f"Note: {note}")
        devices = Device.objects.order_by("region", "name")
        if region:
            devices = devices.filter(region=region)
        counts = {}
        for device in devices:
            counts[device.region] = counts.get(device.region, 0) + 1
            if list_devices:
                self.stdout.write(f"  {device.region:<10} {device.name}")
        for name, count in sorted(counts.items()):
            self.stdout.write(f"{name}: {count}")
        self.stdout.write(self.style.SUCCESS(f"{sum(counts.values())} devices in total."))
