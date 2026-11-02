"""``{% admin_ext_branding as branding %}``, used by the branding base template only."""

from django import template

from ..branding import resolve

register = template.Library()


@register.simple_tag
def admin_ext_branding():
    return resolve()
