"""Generate the demo dataset. Deterministic, synthetic, and safe to re-run.

Nothing here comes from a real system: names, payloads and accounts are generated
from a fixed seed so every run produces the same throwaway data.
"""

import datetime
import random
from decimal import Decimal

from django.contrib.auth.models import Permission, User
from django.core.management.base import BaseCommand
from django.utils import timezone

from demoapp.models import Device, Reading

REGIONS = ["eu-west", "eu-north", "us-east", "ap-south"]
STATUSES = ["idle", "running", "degraded"]

#: How far back the generated readings and device sightings go. Dates are relative to
#: today so the range filters always have something in reach, wherever the demo is run.
WINDOW_DAYS = 30

BIG_INTEGER = 9007199254740993  # 2**53 + 1: JavaScript cannot hold this exactly.


class Command(BaseCommand):
    help = "Populate the disposable demo database with generated data."

    def handle(self, *args, **options):
        verbosity = options.get("verbosity", 1)
        rng = random.Random(20260915)  # fixed seed: demo fixtures, not security
        Reading.objects.all().delete()
        Device.objects.all().delete()

        demo = self._account("demo", "demo", superuser=True)
        operator = self._account("operator", "operator", superuser=False)
        self._grant(operator, ["view_device", "change_device", "view_reading", "change_reading"])

        today = timezone.localdate()
        for index in range(1, 13):
            Device.objects.create(
                name=f"device-{index:02d}",
                region=rng.choice(REGIONS),
                status=rng.choice(STATUSES),
                archived=index % 5 == 0,
                # Alternating late and early local times: 23:55 here is the next day in
                # UTC, which is exactly where a date range has to get the timezone right.
                last_seen_at=self._instant(
                    today - datetime.timedelta(days=index),
                    *((23, 55) if index % 2 else (0, 5)),
                ),
                config={
                    "interval_seconds": rng.choice([15, 30, 60]),
                    "features": rng.sample(["metrics", "logs", "traces", "events"], 2),
                    "thresholds": {"warn": rng.randint(50, 70), "critical": rng.randint(80, 95)},
                },
                last_report={
                    "generated": "2026-09-15T09:00:00Z",
                    "ok": rng.choice([True, False]),
                    "checks": [{"name": "disk", "value": rng.randint(1, 99)}],
                },
            )

        first = Device.objects.order_by("pk").first()
        self._edge_cases(first, rng)
        self._measurements(today, rng)

        if verbosity:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Seeded {Device.objects.count()} devices and "
                    f"{Reading.objects.count()} readings.\n"
                    f"Accounts: demo/demo (superuser, id {demo.pk}), "
                    f"operator/operator (no purge permission, id {operator.pk}).\n"
                    f"All data is generated; the database is disposable."
                )
            )

    def _measurements(self, today, rng):
        """Plain readings spread over the window, for the range filters to bite on.

        Two of every day's readings sit just after midnight and just before it, because
        that is where a date range over a DateTimeField has to get the timezone right.
        """
        devices = list(Device.objects.order_by("pk"))
        for offset in range(WINDOW_DAYS):
            day = today - datetime.timedelta(days=offset)
            for hour, minute in ((0, 5), (13, 20), (23, 55)):
                Reading.objects.create(
                    device=rng.choice(devices),
                    label=f"{day.isoformat()} {hour:02d}:{minute:02d}",
                    payload={"temperature": rng.randint(-10, 40), "unit": "C"},
                    recorded_on=day,
                    recorded_at=self._instant(day, hour, minute),
                    value=Decimal(rng.randrange(0, 10000)) / 100,
                )

    @staticmethod
    def _instant(day, hour, minute):
        """A local wall-clock time on ``day``, made aware the way Django would."""
        moment = datetime.datetime.combine(day, datetime.time(hour, minute))
        return timezone.make_aware(moment) if timezone.is_naive(moment) else moment

    def _edge_cases(self, device, rng):
        """One reading per JSON case the widget has to survive."""
        Reading.objects.create(
            device=device,
            label="nested + typical",
            payload={
                "request": {"method": "POST", "path": "/v1/items", "retries": 0},
                "tags": ["alpha", "beta"],
                "ok": True,
                "ratio": 0.30000000000000004,
            },
        )
        Reading.objects.create(
            device=device,
            label="unicode",
            payload={
                "name": "Персона",
                "emoji": "🚀 ✅",
                "greek": "αβγδε",
                "rtl": "مرحبا",
                "cjk": "日本語のテキスト",
            },
        )
        Reading.objects.create(
            device=device,
            label="big numbers (fidelity)",
            payload={
                "beyond_double": BIG_INTEGER,
                "very_big": 123456789012345678901234567890,
                "exponent": 1e-07,
                "negative_zero": -0.0,
            },
        )
        Reading.objects.create(
            device=device,
            label="html-looking strings (escaping)",
            payload={
                "script": "<script>alert('xss')</script>",
                "img": '<img src=x onerror="alert(1)">',
                "closing": "</textarea><b>bold</b>",
                "ampersand": "a & b < c > d",
            },
        )
        Reading.objects.create(
            device=device,
            label="large payload (plain mode)",
            payload={"rows": [{"i": i, "blob": "x" * 64, "v": rng.random()} for i in range(1200)]},
        )
        Reading.objects.create(device=device, label="empty object", payload={})

    def _account(self, username, password, *, superuser):
        user, _ = User.objects.get_or_create(
            username=username,
            defaults={"email": f"{username}@example.invalid", "is_staff": True},
        )
        user.is_staff = True
        user.is_superuser = superuser
        user.set_password(password)
        user.save()
        return user

    def _grant(self, user, codenames):
        user.user_permissions.set(Permission.objects.filter(codename__in=codenames))
