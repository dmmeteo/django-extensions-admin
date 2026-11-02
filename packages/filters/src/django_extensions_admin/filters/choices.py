"""One value from a dropdown, or several values of one field ORed, in ``list_filter``."""

from __future__ import annotations

from django.contrib.admin.filters import FieldListFilter
from django.contrib.admin.sites import NotRegistered
from django.contrib.admin.utils import get_model_from_relation, reverse_field_path
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import models

from .query import carried_params

__all__ = ["ChoiceFilter", "MultipleChoiceFilter"]

#: Values an ``__isnull`` parameter may carry to mean "the empty choice". Anything else is
#: not something this filter offers, so it matches nothing instead of meaning "not empty".
EMPTY_CHOICE_VALUES = frozenset({"true", "1"})


class ChoiceListFilter(FieldListFilter):
    """Shared plumbing for the choice filters.

    Not part of the public API. The field decides where the options come from and which
    query parameter carries a value - the same parameter Django's own filter for that
    field uses, so a bookmarked URL means the same thing with or without this package.
    The two public classes differ only in how many values they read and which control
    they render.
    """

    template = "django_extensions_admin/filters/choice.html"

    #: Read every submitted value (checkboxes) or only the last one (a dropdown).
    multiple = False

    #: Offer a search box over the options once there are more of them than this.
    search_threshold = 10

    #: Columns without choices whose values survive a round trip through the query string
    #: as text. A date, a float or a JSON document would not, or would not be a choice.
    plain_fields = (models.CharField, models.IntegerField, models.DecimalField, models.UUIDField)

    def __init__(self, field, request, params, model, model_admin, field_path):
        if field.is_relation:
            self.lookup_path = f"{field_path}__{field.target_field.name}"
            self.lookup_kwarg = f"{self.lookup_path}__exact"
            self.to_python = field.target_field.to_python
        elif field.flatchoices:
            self.lookup_path = field_path
            self.lookup_kwarg = f"{field_path}__exact"
            self.to_python = field.to_python
        elif isinstance(field, self.plain_fields):
            self.lookup_path = self.lookup_kwarg = field_path
            self.to_python = field.to_python
        else:
            raise ImproperlyConfigured(
                f"{type(self).__name__} cannot filter {model.__name__}.{field_path}: it expects "
                "a relation, a field with choices, or a CharField, IntegerField, DecimalField "
                f"or UUIDField, not {type(field).__name__}."
            )
        self.lookup_kwarg_isnull = f"{field_path}__isnull"

        # Read the raw values here: FieldListFilter.__init__ pops them out of `params`.
        # "" is the dropdown's own "All", never a value.
        # A dropdown shows one value, so it reads the last one, and it has no empty choice.
        submitted = [str(value) for value in params.get(self.lookup_kwarg) or [] if value != ""]
        empty = [str(value) for value in params.get(self.lookup_kwarg_isnull) or [] if value != ""]
        if not self.multiple:
            submitted, empty = submitted[-1:], []

        super().__init__(field, request, params, model, model_admin, field_path)

        if field.is_relation:
            self.title = getattr(
                field, "verbose_name", get_model_from_relation(field)._meta.verbose_name
            )
        self.options, self.empty_label = self.field_options(request, model, model_admin)
        if not self.multiple:
            self.empty_label = None

        self.values, unreadable = [], False
        for raw in submitted:
            value = self.parse(raw)
            if value is None:
                unreadable = True
            elif value not in self.values:
                self.values.append(value)
        self.empty_selected = any(value.lower() in EMPTY_CHOICE_VALUES for value in empty)
        known = {self.parse(value) for value, _label in self.options}

        self.is_active = bool(submitted or empty)
        self.unrecognised = (
            unreadable
            or any(value not in known for value in self.values)
            or any(value.lower() not in EMPTY_CHOICE_VALUES for value in empty)
            or (self.empty_selected and self.empty_label is None)
        )

    def expected_parameters(self):
        if self.multiple:
            return [self.lookup_kwarg, self.lookup_kwarg_isnull]
        return [self.lookup_kwarg]

    def parse(self, raw):
        """The field's own reading of one value, or None when it cannot read it."""
        try:
            return self.to_python(raw)
        except (ValidationError, ValueError, TypeError):
            return None

    def field_options(self, request, model, model_admin):
        """``([(value, label), ...], empty_label)`` the way Django's own filter finds them.

        ``empty_label`` is None when the field has no empty choice. Blank strings are left
        out: "" already means "All" in the dropdown.
        """
        field = self.field
        if field.is_relation:
            options = field.get_choices(
                include_blank=False, ordering=self.related_ordering(request, model_admin)
            )
            has_empty = field.null or field.many_to_many
            return options, model_admin.get_empty_value_display() if has_empty else None
        if field.flatchoices:
            options = [
                (value, label) for value, label in field.flatchoices if value not in (None, "")
            ]
            empty = [label for value, label in field.flatchoices if value is None]
            return options, empty[0] if empty else None
        # As AllValuesFieldListFilter: the admin's own rows when the column is on its model.
        parent_model, _reverse_path = reverse_field_path(model, self.field_path)
        if model == parent_model:
            queryset = model_admin.get_queryset(request)
        else:
            queryset = parent_model._default_manager.all()
        values = list(queryset.distinct().order_by(field.name).values_list(field.name, flat=True))
        options = [(value, str(value)) for value in values if value not in (None, "")]
        return options, model_admin.get_empty_value_display() if None in values else None

    def related_ordering(self, request, model_admin):
        """The related model's admin ordering, as RelatedFieldListFilter uses it."""
        try:
            related_admin = model_admin.admin_site.get_model_admin(self.field.remote_field.model)
        except NotRegistered:
            return ()
        return related_admin.get_ordering(request)

    def condition(self):
        """The selected values ORed, or None when nothing readable was selected."""
        condition = None
        if self.values:
            condition = models.Q((f"{self.lookup_path}__in", self.values))
        if self.empty_selected and self.empty_label is not None:
            empty = models.Q((self.lookup_kwarg_isnull, True))
            condition = empty if condition is None else condition | empty
        return condition

    def queryset(self, request, queryset):
        """Narrow it, or return nothing at all.

        The filter runs on the queryset the ModelAdmin already authorized, so it can only
        take rows away. A value it cannot read matches nothing: alone it empties the list
        rather than quietly behaving like no filter, and beside readable values it simply
        adds no rows. One ``filter()`` call, so a multi-valued relation joins once and the
        changelist's own duplicate removal applies.
        """
        if not self.is_active:
            return queryset
        condition = self.condition()
        return queryset.none() if condition is None else queryset.filter(condition)

    def get_facet_counts(self, pk_attname, filtered_qs):
        counts = {
            f"{index}__c": models.Count(
                pk_attname, filter=models.Q((self.lookup_path, value)), distinct=True
            )
            for index, (value, _label) in enumerate(self.options)
        }
        if self.empty_label is not None:
            counts["empty__c"] = models.Count(
                pk_attname, filter=models.Q((self.lookup_kwarg_isnull, True)), distinct=True
            )
        return counts

    def choices(self, changelist):
        """One entry carrying the whole template context, as the range filters do."""
        facets = self.get_facet_queryset(changelist) if changelist.add_facets else None
        selected = set(self.values)
        options = []
        for index, (value, label) in enumerate(self.options):
            options.append(
                {
                    "name": self.lookup_kwarg,
                    "value": str(value),
                    "label": f"{label} ({facets[f'{index}__c']})" if facets else label,
                    "selected": self.parse(value) in selected,
                }
            )
        if self.empty_label is not None:
            label = self.empty_label
            options.append(
                {
                    "name": self.lookup_kwarg_isnull,
                    "value": "True",
                    "label": f"{label} ({facets['empty__c']})" if facets else label,
                    "selected": self.empty_selected,
                }
            )
        yield {
            "multiple": self.multiple,
            "name": self.lookup_kwarg,
            "options": options,
            "searchable": len(options) > self.search_threshold,
            "unrecognised": self.unrecognised,
            "carried_params": carried_params(self.request, self.expected_parameters()),
            # {name: None} deletes exactly these keys; `remove=` would match by prefix and
            # take `sequence__range__gte` along with `sequence`.
            "clear_url": changelist.get_query_string(dict.fromkeys(self.expected_parameters())),
            "is_active": self.is_active,
        }


class ChoiceFilter(ChoiceListFilter):
    """One value from a compact dropdown. The empty choice is not offered."""

    multiple = False


class MultipleChoiceFilter(ChoiceListFilter):
    """Several values of one field, ORed, from a list of checkboxes."""

    multiple = True
