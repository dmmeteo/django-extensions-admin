"""Inclusive from/to filters for date, datetime and numeric fields in ``list_filter``."""

from __future__ import annotations

import datetime

from django import forms
from django.conf import settings
from django.contrib.admin.filters import FieldListFilter
from django.contrib.admin.views.main import ERROR_FLAG, PAGE_VAR
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

__all__ = ["DateRangeFilter", "DateTimeRangeFilter", "NumericRangeFilter"]

#: Suffixes of the two query parameters a range filter owns, appended to the field path.
#: They are not ORM lookups: expected_parameters() takes them out of the changelist's
#: lookup parameters before it ever tries to filter with them.
GTE_SUFFIX = "__range__gte"
LTE_SUFFIX = "__range__lte"

#: Query parameters the sidebar form does not carry over. A new range starts at page one,
#: and the changelist's error flag belongs to the request that set it.
DROPPED_PARAMS = frozenset({PAGE_VAR, ERROR_FLAG})


class RangeForm(forms.Form):
    """The two bounds, named after the field they filter.

    ``add_prefix`` is Django's own hook between a field name and its HTML name, so the
    inputs are called ``<field_path>__range__gte`` / ``...__lte`` while the template and
    the cleaning code keep saying ``gte`` and ``lte``.
    """

    def __init__(self, data, *, field_path, lower, upper):
        self.field_path = field_path
        super().__init__(data)
        self.fields["gte"] = lower
        self.fields["lte"] = upper

    def add_prefix(self, field_name):
        return f"{self.field_path}__range__{field_name}"

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("gte"), cleaned.get("lte")
        if start is not None and end is not None and start > end:
            raise forms.ValidationError(_("The start of the range is after its end."))
        return cleaned


class RangeFilter(FieldListFilter):
    """Shared plumbing for the range filters.

    Not part of the public API: each accepted field type gets its own small class instead,
    because "which bounds does this field type mean" is the only thing that differs.
    """

    template = "django_extensions_admin/filters/range.html"

    #: Model field classes this filter can be attached to.
    accepts: tuple[type[models.Field], ...] = ()

    def __init__(self, field, request, params, model, model_admin, field_path):
        if not isinstance(field, self.accepts):
            expected = " or ".join(cls.__name__ for cls in self.accepts)
            raise ImproperlyConfigured(
                f"{type(self).__name__} cannot filter {model.__name__}.{field_path}: "
                f"it expects {expected}, not {type(field).__name__}."
            )
        self.lookup_kwarg_gte = f"{field_path}{GTE_SUFFIX}"
        self.lookup_kwarg_lte = f"{field_path}{LTE_SUFFIX}"
        # Read the raw values here: FieldListFilter.__init__ pops them out of `params`.
        submitted = {}
        for name in (self.lookup_kwarg_gte, self.lookup_kwarg_lte):
            values = params.get(name) or []
            if values and str(values[-1]).strip():
                submitted[name] = values[-1]
        super().__init__(field, request, params, model, model_admin, field_path)
        self.form = RangeForm(
            submitted or None,
            field_path=field_path,
            lower=self.bound_field(_("From")),
            upper=self.bound_field(_("To")),
        )

    def expected_parameters(self):
        return [self.lookup_kwarg_gte, self.lookup_kwarg_lte]

    def bound_field(self, label):
        """Return the form field for one bound. Subclasses decide what a bound looks like."""
        raise NotImplementedError

    def lookups(self, start, end):
        """Translate two cleaned bounds into ORM lookups. Inclusive at both ends."""
        bounds = {}
        if start is not None:
            bounds[f"{self.field_path}__gte"] = start
        if end is not None:
            bounds[f"{self.field_path}__lte"] = end
        return bounds

    def queryset(self, request, queryset):
        """Narrow it, or return nothing at all.

        The filter runs on the queryset the ModelAdmin already authorized, so it can only
        take rows away. Input it cannot read takes every row away rather than quietly
        behaving like no filter at all - the sidebar says why, and nothing raises.
        """
        if not self.form.is_bound:
            return queryset
        if not self.form.is_valid():
            return queryset.none()
        bounds = self.lookups(self.form.cleaned_data["gte"], self.form.cleaned_data["lte"])
        return queryset.filter(**bounds) if bounds else queryset

    def choices(self, changelist):
        """One entry carrying the whole template context.

        ``admin_list_filter`` renders ``spec.template`` with ``title`` and ``choices``, so
        a filter that is a form rather than a list of links passes its context through here.
        """
        yield {
            "form": self.form,
            "carried_params": self.carried_params(),
            "clear_url": changelist.get_query_string(remove=self.expected_parameters()),
            "is_active": self.form.is_bound,
        }

    def carried_params(self):
        """Every other query parameter, as hidden inputs.

        Submitting the range from the sidebar is an ordinary GET, so anything the
        changelist is already doing - the search term, the ordering, the other filters -
        has to travel with it or it would be dropped.
        """
        mine = set(self.expected_parameters())
        return [
            (name, value)
            for name, values in self.request.GET.lists()
            for value in values
            if name not in mine and name not in DROPPED_PARAMS
        ]


class DateRangeFilter(RangeFilter):
    """Two dates, inclusive. On a DateTimeField the end date is included whole."""

    accepts = (models.DateField,)

    def bound_field(self, label):
        return forms.DateField(
            required=False,
            label=label,
            widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        )

    def lookups(self, start, end):
        if not isinstance(self.field, models.DateTimeField):
            return super().lookups(start, end)
        # Half-open at the top: an inclusive `__lte` would have to name the last instant
        # of the day, and would then drop whatever a more precise column still holds.
        bounds = {}
        if start is not None:
            bounds[f"{self.field_path}__gte"] = day_start(start)
        if end is not None:
            bounds[f"{self.field_path}__lt"] = day_start(end + datetime.timedelta(days=1))
        return bounds


class DateTimeRangeFilter(RangeFilter):
    """Two instants, inclusive, read in the active timezone."""

    accepts = (models.DateTimeField,)

    def bound_field(self, label):
        return forms.DateTimeField(
            required=False,
            label=label,
            widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        )


class NumericRangeFilter(RangeFilter):
    """Two numbers, inclusive, parsed by the model field's own form field."""

    accepts = (models.IntegerField, models.FloatField, models.DecimalField)

    def __init__(self, field, request, params, model, model_admin, field_path):
        if field.choices:
            raise ImproperlyConfigured(
                f"NumericRangeFilter cannot filter {model.__name__}.{field_path}: the field "
                "has choices, so Django's own ChoicesFieldListFilter is the right filter."
            )
        super().__init__(field, request, params, model, model_admin, field_path)

    def bound_field(self, label):
        # The model field knows its own precision and limits: DecimalField brings max_digits
        # and the matching input step, IntegerField brings the column's range. `initial` has
        # to go, or a field with a default would pre-fill both bounds with it.
        return self.field.formfield(
            required=False,
            label=label,
            help_text="",
            initial=None,
            localize=False,
        )


def day_start(day):
    """Midnight at the start of ``day`` - the day the reader means, not UTC's."""
    moment = datetime.datetime.combine(day, datetime.time.min)
    return timezone.make_aware(moment) if settings.USE_TZ else moment
