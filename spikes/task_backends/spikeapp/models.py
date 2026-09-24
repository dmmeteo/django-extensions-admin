from django.db import models


class Marker(models.Model):
    """A row the enqueuing transaction writes and the task then tries to read."""

    tag = models.CharField(max_length=64, unique=True)

    def __str__(self):
        return self.tag
