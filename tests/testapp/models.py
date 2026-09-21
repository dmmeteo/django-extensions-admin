from django.db import models


class Device(models.Model):
    name = models.CharField(max_length=100)
    region = models.CharField(max_length=50, default="eu")
    archived = models.BooleanField(default=False)
    config = models.JSONField(default=dict, blank=True)
    notes = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ("pk",)
        permissions = [("purge_device", "Can purge device")]

    def __str__(self):
        return self.name


class Reading(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name="readings")
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("pk",)

    def __str__(self):
        return f"reading {self.pk}"
