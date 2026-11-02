from django.db import models


class Tag(models.Model):
    name = models.CharField(max_length=50, unique=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class Device(models.Model):
    KIND_CHOICES = [
        ("sensor", "Sensor"),
        ("gateway", "Gateway"),
        ("relay", "Relay"),
        (None, "Unclassified"),
    ]

    name = models.CharField(max_length=100)
    region = models.CharField(max_length=50, default="eu")
    archived = models.BooleanField(default=False)
    config = models.JSONField(default=dict, blank=True)
    notes = models.JSONField(null=True, blank=True)
    # NULL on purpose: a None choice is how Django spells an "empty" option for choices.
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, null=True, blank=True)  # noqa: DJ001
    tags = models.ManyToManyField(Tag, blank=True, related_name="devices")

    class Meta:
        ordering = ("pk",)
        permissions = [
            ("purge_device", "Can purge device"),
            ("run_device_commands", "Can run device commands"),
        ]

    def __str__(self):
        return self.name


class Reading(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="readings")
    payload = models.JSONField(default=dict, blank=True)
    recorded_at = models.DateTimeField(null=True, blank=True)
    recorded_on = models.DateField(null=True, blank=True)
    value = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    sequence = models.IntegerField(default=0)
    tag = models.ForeignKey(Tag, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    class Meta:
        ordering = ("pk",)

    def __str__(self):
        return f"reading {self.pk}"
