"""A custom user model with a UUID key, as many projects have: the actor id sent to the
worker and bound into the signed reference must not assume an integer."""

import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
