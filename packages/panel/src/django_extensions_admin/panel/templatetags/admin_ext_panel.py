"""``{% admin_ext_panel_tools as panel %}``, used by the panel templates only."""

from django import template

from .. import available_tools
from ..checks import side

register = template.Library()


@register.simple_tag(takes_context=True)
def admin_ext_panel_tools(context):
    """The tools this request may open, or None: then nothing of the panel renders."""
    if context.get("is_popup"):
        return None
    request = context.get("request")
    tools = available_tools(request)
    if not tools:
        return None
    return {
        "side": side(),
        "tools": [{"tool": tool, "context": tool.context(request)} for tool in tools],
    }
