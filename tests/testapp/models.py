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
    recorded_at = models.DateTimeField(null=True, blank=True)
    recorded_on = models.DateField(null=True, blank=True)
    value = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    sequence = models.IntegerField(default=0)

    class Meta:
        ordering = ("pk",)

    def __str__(self):
        return f"reading {self.pk}"
