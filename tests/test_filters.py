"""Range filters are ordinary list_filter entries: they narrow, they never widen, and a
bound the field cannot read is an error the sidebar shows rather than a wider result set."""

import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.test import RequestFactory, TestCase
from django.utils import timezone

from django_extensions_admin import DateRangeFilter, DateTimeRangeFilter, NumericRangeFilter

from .testapp.models import Device, Reading

READINGS = "/admin/testapp/reading/"
INSTANTS = "/instant/testapp/reading/"
RECENT = "/recent/testapp/reading/"


def build_filter(filter_class, model, field_name, query=""):
    """Instantiate a filter the way FieldListFilter.create does, without a changelist."""
    request = RequestFactory().get(f"/?{query}")
    field = model._meta.get_field(field_name)
    return filter_class(
        field, request, dict(request.GET.lists()), model, None, field_path=field_name
    )


class RangeFilterTestCase(TestCase):
    """Four readings, one per day, each at a different time of the local day."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser("root", "root@example.invalid", "pw")
        cls.device = Device.objects.create(name="alpha", region="eu")
        cls.other = Device.objects.create(name="beta", region="us")
        cls.readings = []
        for index, (day, hour) in enumerate([(1, 0), (2, 23), (3, 0), (4, 12)]):
            cls.readings.append(
                Reading.objects.create(
                    device=cls.device if index < 3 else cls.other,
                    recorded_on=datetime.date(2026, 3, day),
                    recorded_at=timezone.make_aware(datetime.datetime(2026, 3, day, hour, 30)),
                    value=Decimal(index * 10),
                    sequence=index,
                )
            )

    def setUp(self):
        self.client.force_login(self.superuser)

    def ids(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.response = response
        return list(response.context["cl"].queryset.values_list("sequence", flat=True))


class BoundsTests(RangeFilterTestCase):
    def test_both_date_bounds_are_inclusive(self):
        found = self.ids(
            f"{READINGS}?recorded_on__range__gte=2026-03-02&recorded_on__range__lte=2026-03-03"
        )
        self.assertEqual(found, [1, 2])

    def test_a_datetime_column_includes_the_whole_end_day(self):
        """23:30 on the end date is inside the range; 00:30 the next day is not."""
        found = self.ids(
            f"{READINGS}?recorded_at__range__gte=2026-03-01&recorded_at__range__lte=2026-03-02"
        )
        self.assertEqual(found, [0, 1])

    def test_day_boundaries_follow_the_active_timezone(self):
        """23:30 on 2 March in Chicago is 3 March in UTC, and one query answers both ways."""
        query = "?recorded_at__range__gte=2026-03-03&recorded_at__range__lte=2026-03-03"
        with timezone.override("America/Chicago"):
            self.assertEqual(self.ids(READINGS + query), [2])
        with timezone.override("UTC"):
            self.assertEqual(self.ids(READINGS + query), [1, 2])

    def test_numeric_bounds_are_inclusive(self):
        self.assertEqual(self.ids(f"{READINGS}?value__range__gte=10&value__range__lte=20"), [1, 2])

    def test_a_decimal_bound_keeps_its_fraction(self):
        self.readings[2].value = Decimal("20.49")
        self.readings[2].save(update_fields=["value"])
        self.assertEqual(self.ids(f"{READINGS}?value__range__gte=20.5"), [3])

    def test_only_a_lower_bound_is_a_one_sided_filter(self):
        self.assertEqual(self.ids(f"{READINGS}?sequence__range__gte=2"), [2, 3])

    def test_only_an_upper_bound_is_a_one_sided_filter(self):
        self.assertEqual(self.ids(f"{READINGS}?sequence__range__lte=1"), [0, 1])

    def test_no_bound_at_all_filters_nothing(self):
        self.assertEqual(self.ids(READINGS), [0, 1, 2, 3])
        self.assertContains(self.response, 'data-filter-title="value"')

    def test_an_empty_parameter_is_the_same_as_no_bound(self):
        query = "?sequence__range__gte=&sequence__range__lte=2"
        self.assertEqual(self.ids(READINGS + query), [0, 1, 2])

    def test_minutes_are_read_in_the_active_timezone(self):
        query = "?recorded_at__range__gte=2026-03-02T23:00&recorded_at__range__lte=2026-03-02T23:30"
        with timezone.override("America/Chicago"):
            self.assertEqual(self.ids(INSTANTS + query), [1])
        with timezone.override("UTC"):
            self.assertEqual(self.ids(INSTANTS + query), [])


class BadInputTests(RangeFilterTestCase):
    def test_an_unreadable_bound_matches_nothing_and_says_why(self):
        """A bound the field cannot parse must not quietly behave like no filter at all."""
        self.assertEqual(self.ids(f"{READINGS}?value__range__gte=nope"), [])
        self.assertContains(self.response, "admin-ext-range-error")
        self.assertContains(self.response, "Enter a number.")

    def test_an_unreadable_date_matches_nothing(self):
        self.assertEqual(self.ids(f"{READINGS}?recorded_on__range__lte=2026-02-30"), [])
        self.assertContains(self.response, "Enter a valid date.")

    def test_a_reversed_range_reports_itself_and_matches_nothing(self):
        found = self.ids(
            f"{READINGS}?recorded_on__range__gte=2026-03-04&recorded_on__range__lte=2026-03-01"
        )
        self.assertEqual(found, [])
        self.assertContains(self.response, "The start of the range is after its end.")

    def test_a_bad_bound_redisplays_what_was_typed(self):
        self.ids(f"{READINGS}?value__range__gte=nope")
        self.assertContains(self.response, 'value="nope"')

    def test_a_bad_bound_does_not_disturb_the_other_filters(self):
        found = self.ids(f"{READINGS}?sequence__range__gte=2&value__range__gte=nope")
        self.assertEqual(found, [])
        self.assertContains(self.response, 'value="2"')


class CompositionTests(RangeFilterTestCase):
    def test_the_range_composes_with_search_ordering_and_other_filters(self):
        found = self.ids(f"{READINGS}?q=alpha&o=-1&device__region=eu&sequence__range__gte=1")
        self.assertEqual(found, [2, 1])

    def test_the_form_carries_the_rest_of_the_query_string(self):
        self.ids(f"{READINGS}?q=alpha&o=1&device__region=eu&sequence__range__gte=1")
        for carried in (
            '<input type="hidden" name="q" value="alpha">',
            '<input type="hidden" name="o" value="1">',
            '<input type="hidden" name="device__region" value="eu">',
        ):
            self.assertContains(self.response, carried)

    def test_the_form_does_not_carry_its_own_bounds_or_the_page_number(self):
        """Its own bounds are already the visible inputs, and a new range starts at page one."""
        spec = build_filter(
            NumericRangeFilter, Reading, "sequence", "p=2&q=alpha&sequence__range__gte=1"
        )
        self.assertEqual(spec.carried_params(), [("q", "alpha")])
        self.ids(f"{READINGS}?p=1&sequence__range__gte=1")
        self.assertNotContains(self.response, '<input type="hidden" name="p"')

    def test_clearing_removes_only_this_filters_parameters(self):
        self.ids(f"{READINGS}?q=alpha&sequence__range__gte=1&value__range__lte=30")
        self.assertContains(self.response, "?q=alpha&amp;value__range__lte=30")

    def test_the_filter_can_only_narrow_the_admins_own_queryset(self):
        """RecentReadingAdmin hides sequence &lt; 3; a wider range cannot bring it back."""
        self.assertEqual(self.ids(f"{RECENT}?value__range__gte=0"), [3])


class ConfigurationTests(TestCase):
    def test_the_two_parameters_belong_to_the_filter(self):
        """Declared as expected parameters, so the changelist never treats them as lookups."""
        spec = build_filter(NumericRangeFilter, Reading, "sequence")
        self.assertEqual(
            spec.expected_parameters(), ["sequence__range__gte", "sequence__range__lte"]
        )

    def test_a_date_filter_refuses_a_numeric_field(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "not IntegerField"):
            build_filter(DateRangeFilter, Reading, "sequence")

    def test_a_numeric_filter_refuses_a_date_field(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "not DateField"):
            build_filter(NumericRangeFilter, Reading, "recorded_on")

    def test_the_datetime_filter_refuses_a_plain_date_field(self):
        """A DateField has no time of day, so minute-precision bounds would be a lie."""
        with self.assertRaisesMessage(ImproperlyConfigured, "it expects DateTimeField"):
            build_filter(DateTimeRangeFilter, Reading, "recorded_on")

    def test_the_date_filter_accepts_both_date_and_datetime_fields(self):
        self.assertIsInstance(
            build_filter(DateRangeFilter, Reading, "recorded_at").field, models.DateTimeField
        )

    def test_a_numeric_field_with_choices_is_sent_to_djangos_own_filter(self):
        field = Reading._meta.get_field("sequence")
        original, field.choices = field.choices, [(1, "one"), (2, "two")]
        try:
            with self.assertRaisesMessage(ImproperlyConfigured, "ChoicesFieldListFilter"):
                build_filter(NumericRangeFilter, Reading, "sequence")
        finally:
            field.choices = original

    def test_a_field_default_does_not_prefill_the_bounds(self):
        """sequence defaults to 0; an empty filter form must still be empty."""
        spec = build_filter(NumericRangeFilter, Reading, "sequence")
        self.assertFalse(spec.form.is_bound)
        self.assertNotIn("value=", str(spec.form["gte"]))

    def test_the_inputs_are_named_after_the_field(self):
        spec = build_filter(DateRangeFilter, Reading, "recorded_on")
        self.assertIn('name="recorded_on__range__gte"', str(spec.form["gte"]))
        self.assertIn('type="date"', str(spec.form["gte"]))


class MarkupTests(RangeFilterTestCase):
    def test_the_filter_uses_the_stock_sidebar_markup(self):
        self.ids(READINGS)
        self.assertContains(self.response, '<details data-filter-title="recorded on" open>')
        self.assertContains(self.response, "By recorded on")

    def test_the_stylesheet_ships_with_the_filter(self):
        self.ids(READINGS)
        self.assertContains(self.response, "django_extensions_admin/filters.css")

    def test_the_form_is_a_get_form_with_no_javascript(self):
        self.ids(READINGS)
        self.assertContains(self.response, '<form class="admin-ext-range" method="get" action="">')
        self.assertNotContains(self.response, "admin-ext-range.js")
