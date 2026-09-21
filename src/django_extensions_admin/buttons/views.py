"""The endpoint behind every button.

Rendering a button is a hint; this module is where access is actually decided.
Every check the template makes is repeated here, so guessing a URL gains nothing.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.admin.templatetags.admin_urls import add_preserved_filters
from django.contrib.admin.utils import quote, unquote
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse, HttpResponseNotAllowed, HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext as _

from .decorators import Button

CONFIRMED_FIELD = "_admin_ext_confirmed"

#: Where to go after the handler runs. One handler can be placed on both the change
#: form and the list rows, so the rendered control says which page it came from.
#: Anything else - including a hand-written POST - lands on the changelist.
RETURN_FIELD = "_admin_ext_return"
RETURN_CHANGELIST = "changelist"
RETURN_CHANGEFORM = "changeform"

LEVELS = {
    "debug": messages.DEBUG,
    "info": messages.INFO,
    "success": messages.SUCCESS,
    "warning": messages.WARNING,
    "error": messages.ERROR,
}


def button_url(model_admin, button: Button, obj=None) -> str:
    opts = model_admin.model._meta
    base = f"admin:{opts.app_label}_{opts.model_name}_adminext_{button.name}"
    site = model_admin.admin_site.name
    if not button.takes_object:
        return reverse(base, current_app=site)
    return reverse(base, args=[quote(obj.pk)], current_app=site)


def preserved_url(model_admin, request, url: str) -> str:
    context = {
        "preserved_filters": model_admin.get_preserved_filters(request),
        "opts": model_admin.model._meta,
    }
    return add_preserved_filters(context, url)


def _redirect_target(model_admin, request, obj):
    opts = model_admin.model._meta
    site = model_admin.admin_site.name
    if obj is not None and request.POST.get(RETURN_FIELD) == RETURN_CHANGEFORM:
        url = reverse(
            f"admin:{opts.app_label}_{opts.model_name}_change",
            args=[quote(obj.pk)],
            current_app=site,
        )
    else:
        url = reverse(f"admin:{opts.app_label}_{opts.model_name}_changelist", current_app=site)
    return preserved_url(model_admin, request, url)


def _apply_result(model_admin, request, button: Button, result) -> None:
    """Turn a handler's return value into a user message."""
    level = messages.SUCCESS
    if result is None:
        text = button.default_message()
    elif isinstance(result, tuple) and len(result) == 2:
        text, level = result
        if isinstance(level, str):
            level = LEVELS[level]
    else:
        text = str(result)
    if text:
        model_admin.message_user(request, text, level)


def run_button(model_admin, button: Button, request, object_id=None):
    """Shared view body for one button."""
    obj = None
    if button.takes_object:
        if object_id is None:
            raise Http404("This button needs an object.")
        # get_object() goes through get_queryset(request): an id the user may not see
        # is indistinguishable from one that does not exist.
        obj = model_admin.get_object(request, unquote(str(object_id)))
        if obj is None:
            raise Http404(f"No {model_admin.model._meta.verbose_name} matches the given query.")

    if not button.is_allowed(model_admin, request, obj):
        raise PermissionDenied

    if request.method != "POST":
        # Buttons are POST-only: no state changes from a link, a prefetch or a crawler,
        # and Django's CSRF middleware covers every one of them.
        return HttpResponseNotAllowed(["POST"])

    if button.confirm and request.POST.get(CONFIRMED_FIELD) != "1":
        return _confirmation_page(model_admin, button, request, obj)

    handler = getattr(model_admin, button.name)
    result = handler(request, obj) if button.takes_object else handler(request)

    if isinstance(result, HttpResponse):
        return result
    _apply_result(model_admin, request, button, result)
    return HttpResponseRedirect(_redirect_target(model_admin, request, obj))


def _confirmation_page(model_admin, button: Button, request, obj):
    opts = model_admin.model._meta
    if button.confirm_text:
        question = button.confirm_text
    elif obj is not None:
        question = format_html(
            _('Are you sure you want to run "{label}" on {name} "{obj}"?'),
            label=button.description,
            name=opts.verbose_name,
            obj=obj,
        )
    else:
        question = format_html(
            _('Are you sure you want to run "{label}"?'),
            label=button.description,
        )
    context = {
        **model_admin.admin_site.each_context(request),
        "title": button.description,
        "button": button,
        "question": question,
        "object": obj,
        "opts": opts,
        "action_url": request.get_full_path(),
        "confirmed_field": CONFIRMED_FIELD,
        "return_field": RETURN_FIELD,
        # Carry the caller's page through the interstitial, so confirming a row button
        # still returns to the list and a change-form button to its object.
        "return_target": request.POST.get(RETURN_FIELD) or RETURN_CHANGELIST,
        "media": model_admin.media,
    }
    return TemplateResponse(request, "django_extensions_admin/buttons/confirm.html", context)
