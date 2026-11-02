"""The shared tools panel: one resizable side panel that admin tools open in.

A tool app registers a ``Tool`` in its ``AppConfig.ready()``. The panel and its header
button render only for a request that at least one registered tool is available to.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from django.http import HttpRequest

__all__ = ["Tool", "available_tools", "register"]


@dataclass(frozen=True)
class Tool:
    key: str
    label: str
    template: str
    # Decides per request; the tool's own views must still check on every request.
    available: Callable[[HttpRequest], bool]
    context: Callable[[HttpRequest], dict[str, Any]] = lambda request: {}
    css: tuple[str, ...] = ()
    js_modules: tuple[str, ...] = ()


_tools: dict[str, Tool] = {}


def register(tool: Tool) -> None:
    _tools[tool.key] = tool


def available_tools(request: HttpRequest | None) -> list[Tool]:
    if request is None:
        return []
    return [tool for tool in _tools.values() if tool.available(request)]
