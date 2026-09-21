from django.db import models


class Device(models.Model):
    """Entirely synthetic: generated names, no real-world data of any kind."""

    name = models.CharField(max_length=100)
    region = models.CharField(max_length=32, default="eu-west")
    status = models.CharField(max_length=32, default="idle")
    archived = models.BooleanField(default=False)
    config = models.JSONField(default=dict, blank=True)
    last_report = models.JSONField(null=True, blank=True, help_text="Rendered read-only.")

    class Meta:
        ordering = ("pk",)
        permissions = [("purge_device", "Can purge devices")]

    def __str__(self):
        return self.name


class Reading(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="readings")
    label = models.CharField(max_length=100, blank=True)
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("pk",)

    def __str__(self):
        return self.label or f"reading {self.pk}"
