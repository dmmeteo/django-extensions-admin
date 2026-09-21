"""The endpoint behind every button.

Rendering a button is a hint; this module is where access is actually decided.
Every check the template makes is repeated here, so guessing a URL gains nothing.
"""

from __future__ import annotations

import copy

from django.contrib import messages
from django.contrib.admin.options import IncorrectLookupParameters
from django.contrib.admin.templatetags.admin_urls import add_preserved_filters
from django.contrib.admin.utils import unquote
from django.core.exceptions import PermissionDenied
from django.http import (
    Http404,
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseNotAllowed,
    HttpResponseRedirect,
    QueryDict,
)
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext as _

from .decorators import LEVELS, Button

CONFIRMED_FIELD = "_admin_ext_confirmed"


def button_url(model_admin, button: Button, obj=None) -> str:
    opts = model_admin.model._meta
    base = f"admin:{opts.app_label}_{opts.model_name}_adminext_{button.name}"
    if button.scope == "changelist":
        return reverse(base, current_app=model_admin.admin_site.name)
    return reverse(base, args=[quote_pk(obj)], current_app=model_admin.admin_site.name)


def quote_pk(obj):
    from django.contrib.admin.utils import quote

    return quote(obj.pk)


def preserved_url(model_admin, request, url: str) -> str:
    context = {
        "preserved_filters": model_admin.get_preserved_filters(request),
        "opts": model_admin.model._meta,
    }
    return add_preserved_filters(context, url)


def filtered_queryset(model_admin, request):
    """The rows the changelist is currently showing, rebuilt from preserved filters.

    The base is always ``model_admin.get_queryset(request)``, so per-request row
    restrictions still apply; the filters can only narrow it further.
    """
    raw = request.GET.get("_changelist_filters") or ""
    list_request = copy.copy(request)
    list_request.GET = QueryDict(raw)
    list_request.method = "GET"
    list_request.POST = QueryDict()
    changelist = model_admin.get_changelist_instance(list_request)
    return changelist.get_queryset(list_request)


def _redirect_target(model_admin, request, button: Button, obj):
    opts = model_admin.model._meta
    site = model_admin.admin_site.name
    if button.scope == "object" and obj is not None:
        url = reverse(
            f"admin:{opts.app_label}_{opts.model_name}_change",
            args=[quote_pk(obj)],
            current_app=site,
        )
    else:
        url = reverse(f"admin:{opts.app_label}_{opts.model_name}_changelist", current_app=site)
    return preserved_url(model_admin, request, url)


def _apply_result(model_admin, request, button: Button, result) -> str | None:
    """Turn a handler's return value into a user message. Returns nothing."""
    level = messages.SUCCESS
    text = None
    if result is None:
        text = button.default_message(model_admin)
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
    if button.scope in ("object", "row"):
        if object_id is None:
            raise Http404("This button needs an object.")
        # get_object() goes through get_queryset(request): an id the user may not see
        # is indistinguishable from one that does not exist.
        obj = model_admin.get_object(request, unquote(str(object_id)))
        if obj is None:
            raise Http404(f"No {model_admin.model._meta.verbose_name} matches the given query.")

    if not button.is_allowed(model_admin, request, obj):
        raise PermissionDenied

    if request.method not in ("GET", "POST"):
        return HttpResponseNotAllowed(["POST"])
    if not button.read_only and request.method != "POST":
        # Mutating buttons are POST-only: no state changes from a link, a prefetch
        # or a crawler.
        return HttpResponseNotAllowed(["POST"])

    if button.confirm and request.POST.get(CONFIRMED_FIELD) != "1":
        return _confirmation_page(model_admin, button, request, obj)

    handler = getattr(model_admin, button.handler_name)
    if button.scope == "changelist":
        if button.filtered:
            try:
                queryset = filtered_queryset(model_admin, request)
            except IncorrectLookupParameters:
                return HttpResponseBadRequest("Invalid changelist filters.")
        else:
            queryset = model_admin.get_queryset(request)
        result = handler(request, queryset)
    else:
        result = handler(request, obj)

    if isinstance(result, HttpResponse):
        return result
    _apply_result(model_admin, request, button, result)
    return HttpResponseRedirect(_redirect_target(model_admin, request, button, obj))


def _confirmation_page(model_admin, button: Button, request, obj):
    opts = model_admin.model._meta
    if button.confirm_text:
        question = button.confirm_text
    elif obj is not None:
        question = format_html(
            _('Are you sure you want to run "{label}" on {name} "{obj}"?'),
            label=button.label,
            name=opts.verbose_name,
            obj=obj,
        )
    else:
        question = format_html(
            _('Are you sure you want to run "{label}"?'),
            label=button.label,
        )
    context = {
        **model_admin.admin_site.each_context(request),
        "title": button.label,
        "button": button,
        "question": question,
        "object": obj,
        "opts": opts,
        "action_url": request.get_full_path(),
        "confirmed_field": CONFIRMED_FIELD,
        "media": model_admin.media,
    }
    return TemplateResponse(request, "django_extensions_admin/buttons/confirm.html", context)
