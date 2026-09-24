from django.db import models


class Tag(models.Model):
    """Generated labels, enough of them that the tag filter wants a search box."""

    name = models.CharField(max_length=50, unique=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class Device(models.Model):
    """Entirely synthetic: generated names, no real-world data of any kind."""

    name = models.CharField(max_length=100)
    region = models.CharField(max_length=32, default="eu-west")
    status = models.CharField(max_length=32, default="idle")
    archived = models.BooleanField(default=False)
    config = models.JSONField(default=dict, blank=True)
    last_report = models.JSONField(null=True, blank=True, help_text="Rendered read-only.")
    last_seen_at = models.DateTimeField(null=True, blank=True)
    tags = models.ManyToManyField(Tag, blank=True, related_name="devices")

    class Meta:
        ordering = ("pk",)
        permissions = [("purge_device", "Can purge devices")]

    def __str__(self):
        return self.name


class Reading(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="readings")
    label = models.CharField(max_length=100, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    recorded_on = models.DateField(null=True, blank=True)
    recorded_at = models.DateTimeField(null=True, blank=True)
    value = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ("pk",)

    def __str__(self):
        return self.label or f"reading {self.pk}"
