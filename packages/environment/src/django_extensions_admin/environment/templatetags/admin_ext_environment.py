"""``{% admin_ext_environment as environment %}``, used by the indicator templates only."""

from django import template

from ..indicator import resolve

register = template.Library()


@register.simple_tag
def admin_ext_environment():
    return resolve()
