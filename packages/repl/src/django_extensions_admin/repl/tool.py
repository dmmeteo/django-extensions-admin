from typing import Any

from django.http import HttpRequest

from .access import is_repl_user
from .conf import get_config


def available(request: HttpRequest) -> bool:
    try:
        enabled = get_config().enabled
    except Exception:  # an invalid setting is a system check error, not a broken admin page
        return False
    return enabled and is_repl_user(getattr(request, "user", None))


def context(request: HttpRequest) -> dict[str, Any]:
    return {"stream_path": get_config().stream_path}
