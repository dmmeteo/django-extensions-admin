from channels.security.websocket import AllowedHostsOriginValidator
from django.urls import path

from .conf import get_config
from .consumers import ReplConsumer

# The origin check travels with the route, so a project that forgets it in asgi.py still has it.
websocket_urlpatterns = [
    path(get_config().stream_path.lstrip("/"), AllowedHostsOriginValidator(ReplConsumer.as_asgi()))
]
