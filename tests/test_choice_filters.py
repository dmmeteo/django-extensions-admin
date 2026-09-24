"""Choice filters are ordinary list_filter entries: one value from a dropdown, or several
values of one field ORed together. They use Django's own parameter names, repeat a key
rather than join values into one, and never widen the admin's own queryset."""

from urllib.parse import urlencode

from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from django.test import RequestFactory, TestCase

from django_extensions_admin import ChoiceFilter, MultipleChoiceFilter

from .testapp.admin import ChoiceDeviceAdmin, ChoiceReadingAdmin, choices_site
from .testapp.models import Device, Reading, Tag

DEVICES = "/choices/testapp/device/"
READINGS = "/choices/testapp/reading/"

NOTE = "A selected value is not one of the choices."


def url(base, *pairs):
    """A changelist URL. Pairs, not a dict, so a key can repeat."""
    return f"{base}?{urlencode(pairs)}" if pairs else base


def build_filter(filter_class, model_admin, field_path, *pairs):
    """Instantiate a filter the way the changelist does, without rendering one."""
    request = RequestFactory().get(url("/", *pairs))
    model = model_admin.model
    field = model._meta.get_field(field_path)
    return filter_class(
        field, request, dict(request.GET.lists()), model, model_admin, field_path=field_path
    )


class ChoiceFilterTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser("root", "root@example.invalid", "pw")
        cls.alpha = Tag.objects.create(name="alpha")
        cls.beta = Tag.objects.create(name="beta")
        cls.punctuated = Tag.objects.create(name="a, b & c")
        cls.quoted = Tag.objects.create(name='50% «ü» "q"')

        def device(name, region, kind, tags, archived=False):
            obj = Device.objects.create(name=name, region=region, kind=kind, archived=archived)
            obj.tags.set(tags)
            return obj

        cls.one = device("one", "eu", "sensor", [cls.alpha, cls.beta])
        cls.two = device("two", "us", "gateway", [cls.beta])
        cls.three = device("three", "eu, west & more", None, [cls.punctuated])
        cls.four = device("four", "ap", "relay", [])
        cls.hidden = device("hidden", "eu", "sensor", [cls.alpha], archived=True)

        for sequence, (owner, tag) in enumerate(
            [
                (cls.one, cls.alpha),
                (cls.two, None),
                (cls.three, cls.beta),
                (cls.four, None),
                (cls.hidden, cls.alpha),
            ]
        ):
            Reading.objects.create(device=owner, tag=tag, sequence=sequence)

    def setUp(self):
        self.client.force_login(self.superuser)
        self.device_admin = ChoiceDeviceAdmin(Device, choices_site)
        self.reading_admin = ChoiceReadingAdmin(Reading, choices_site)

    def get(self, target):
        response = self.client.get(target)
        self.assertEqual(response.status_code, 200)
        self.response = response
        self.cl = response.context["cl"]
        return response

    def section(self, title):
        """The rendered HTML of one filter in the sidebar, and nothing else on the page."""
        html = self.response.content.decode()
        return html.split(f'<details data-filter-title="{title}"')[1].split("</details>")[0]

    def names(self, target):
        self.get(target)
        return list(self.cl.queryset.values_list("name", flat=True))

    def sequences(self, target):
        self.get(target)
        return list(self.cl.queryset.values_list("sequence", flat=True))


class SingleChoiceTests(ChoiceFilterTestCase):
    def test_one_choice_narrows_the_list(self):
        """ "hidden" is a sensor too, but the admin never shows it."""
        self.assertEqual(self.names(url(DEVICES, ("kind__exact", "sensor"))), ["one"])

    def test_a_foreign_key_uses_djangos_own_parameter(self):
        found = self.sequences(url(READINGS, ("device__id__exact", self.two.pk)))
        self.assertEqual(found, [1])

    def test_the_dropdown_shows_what_is_selected(self):
        self.get(url(DEVICES, ("kind__exact", "gateway")))
        kind = self.section("kind")
        self.assertIn('<option value="gateway" selected>Gateway</option>', kind)
        self.assertIn('<option value="">All</option>', kind)

    def test_nothing_selected_selects_all(self):
        self.assertEqual(self.names(DEVICES), ["one", "two", "three", "four"])
        self.assertContains(self.response, '<option value="">All</option>')

    def test_a_repeated_value_means_the_last_one(self):
        """A dropdown can show one value, so it filters by the one it can show."""
        found = self.names(url(DEVICES, ("kind__exact", "sensor"), ("kind__exact", "gateway")))
        self.assertEqual(found, ["two"])

    def test_the_empty_choice_is_not_offered_in_a_dropdown(self):
        """One <select> has one name: it cannot also send kind__isnull."""
        self.get(DEVICES)
        self.assertNotIn("Unclassified", self.section("kind"))
        spec = build_filter(ChoiceFilter, self.device_admin, "kind")
        self.assertEqual(spec.expected_parameters(), ["kind__exact"])

    def test_all_submits_an_empty_value_which_filters_nothing(self):
        self.assertEqual(
            self.names(url(DEVICES, ("kind__exact", ""))), ["one", "two", "three", "four"]
        )
        self.assertNotContains(self.response, NOTE)


class MultipleChoiceTests(ChoiceFilterTestCase):
    def test_values_of_one_field_are_ored(self):
        found = self.names(url(DEVICES, ("region", "us"), ("region", "ap")))
        self.assertEqual(found, ["two", "four"])

    def test_a_many_to_many_match_on_two_values_is_one_row(self):
        """ "one" carries both tags; the join would list it twice."""
        found = self.names(
            url(DEVICES, ("tags__id__exact", self.alpha.pk), ("tags__id__exact", self.beta.pk))
        )
        self.assertEqual(found, ["one", "two"])
        self.assertEqual(self.cl.result_count, 2)
        self.assertEqual(len(self.cl.result_list), 2)

    def test_the_empty_choice_is_ored_with_the_values(self):
        found = self.names(
            url(DEVICES, ("tags__id__exact", self.beta.pk), ("tags__isnull", "True"))
        )
        self.assertEqual(found, ["one", "two", "four"])

    def test_a_nullable_foreign_key_offers_the_empty_choice(self):
        found = self.sequences(
            url(READINGS, ("tag__id__exact", self.beta.pk), ("tag__isnull", "True"))
        )
        self.assertEqual(found, [1, 2, 3])

    def test_a_choices_field_offers_its_own_empty_label(self):
        spec = build_filter(MultipleChoiceFilter, self.device_admin, "kind", ("kind__isnull", "1"))
        self.assertEqual(spec.empty_label, "Unclassified")
        self.assertEqual(list(spec.queryset(None, Device.objects.all())), [self.three])
        self.assertEqual(spec.expected_parameters(), ["kind__exact", "kind__isnull"])

    def test_a_path_through_a_relation_offers_the_related_values(self):
        found = self.sequences(url(READINGS, ("device__region", "us"), ("device__region", "ap")))
        self.assertEqual(found, [1, 3])

    def test_an_integer_column_parses_its_values(self):
        self.assertEqual(
            self.sequences(url(READINGS, ("sequence", "01"), ("sequence", "3"))), [1, 3]
        )

    def test_different_fields_still_narrow_each_other(self):
        found = self.names(url(DEVICES, ("tags__id__exact", self.beta.pk), ("region", "us")))
        self.assertEqual(found, ["two"])

    def test_checked_boxes_are_the_selected_values(self):
        self.get(url(DEVICES, ("tags__id__exact", self.beta.pk), ("tags__isnull", "True")))
        self.assertContains(
            self.response,
            f'<input type="checkbox" name="tags__id__exact" value="{self.beta.pk}" checked>',
        )
        self.assertContains(
            self.response, '<input type="checkbox" name="tags__isnull" value="True" checked>'
        )
        self.assertContains(
            self.response,
            f'<input type="checkbox" name="tags__id__exact" value="{self.alpha.pk}">',
        )

    def test_selected_rows_use_the_stock_selected_marker(self):
        self.get(url(DEVICES, ("region", "us")))
        self.assertContains(self.response, '<li class="selected"><label>', count=1)


class PunctuationTests(ChoiceFilterTestCase):
    """A value is never split, masked or trimmed: each one is its own repeated key."""

    def test_a_value_with_a_comma_and_an_ampersand_filters_as_itself(self):
        found = self.names(url(DEVICES, ("region", "eu, west & more"), ("region", "us")))
        self.assertEqual(found, ["two", "three"])

    def test_it_comes_back_checked_and_escaped(self):
        self.get(url(DEVICES, ("region", "eu, west & more")))
        self.assertContains(
            self.response,
            '<input type="checkbox" name="region" value="eu, west &amp; more" checked>',
        )

    def test_labels_are_escaped(self):
        self.get(DEVICES)
        self.assertContains(self.response, "a, b &amp; c")
        self.assertContains(self.response, "50% «ü» &quot;q&quot;")

    def test_another_filters_form_carries_every_value_separately(self):
        self.get(url(DEVICES, ("region", "eu, west & more"), ("region", "us")))
        for value in ("eu, west &amp; more", "us"):
            self.assertContains(
                self.response, f'<input type="hidden" name="region" value="{value}">'
            )

    def test_another_filters_links_keep_every_value(self):
        self.get(url(READINGS, ("sequence", "1"), ("sequence", "3")))
        self.assertContains(
            self.response, "device__archived__exact=1&amp;sequence=1&amp;sequence=3"
        )


class CompositionTests(ChoiceFilterTestCase):
    def test_the_filter_composes_with_search_and_ordering(self):
        found = self.names(
            url(
                DEVICES,
                ("q", "o"),
                ("o", "-1"),
                ("tags__id__exact", self.beta.pk),
                ("region", "eu"),
                ("region", "us"),
            )
        )
        self.assertEqual(found, ["two", "one"])

    def test_the_form_carries_the_rest_of_the_query_string(self):
        self.get(url(DEVICES, ("q", "o"), ("o", "1"), ("kind__exact", "sensor")))
        for carried in (
            '<input type="hidden" name="q" value="o">',
            '<input type="hidden" name="o" value="1">',
            '<input type="hidden" name="kind__exact" value="sensor">',
        ):
            self.assertContains(self.response, carried)

    def test_the_form_does_not_carry_its_own_values_or_the_page(self):
        """Its own values are the visible boxes, and a new selection starts at page one."""
        self.get(url(READINGS, ("p", "1"), ("tag__isnull", "True"), ("q", "o")))
        tag = self.section("tag")
        self.assertIn('<input type="hidden" name="q" value="o">', tag)
        self.assertNotIn('<input type="hidden" name="p"', tag)
        self.assertNotIn('<input type="hidden" name="tag__isnull"', tag)
        # The other filters' forms do carry it: it is part of what the list is doing.
        self.assertIn('<input type="hidden" name="tag__isnull"', self.section("sequence"))

    def test_clearing_removes_exactly_this_filters_parameters(self):
        """`sequence` is a prefix of the range filter's `sequence__range__gte`; it stays."""
        self.get(url(READINGS, ("q", "o"), ("sequence", "1"), ("sequence__range__gte", "1")))
        self.assertContains(self.response, 'href="?q=o&amp;sequence__range__gte=1"')

    def test_a_choice_and_a_range_on_one_column_both_apply(self):
        found = self.sequences(
            url(READINGS, ("sequence", "1"), ("sequence", "3"), ("sequence__range__gte", "2"))
        )
        self.assertEqual(found, [3])

    def test_nothing_selected_shows_no_clear_link(self):
        self.get(DEVICES)
        self.assertNotContains(self.response, "admin-ext-choice-clear")

    def test_the_filter_can_only_narrow_the_admins_own_queryset(self):
        found = self.names(url(DEVICES, ("tags__id__exact", self.alpha.pk)))
        self.assertEqual(found, ["one"])


class TamperedInputTests(ChoiceFilterTestCase):
    """What the sidebar cannot offer matches nothing, says so, and never raises."""

    def test_an_unreadable_key_matches_nothing(self):
        self.assertEqual(self.names(url(DEVICES, ("tags__id__exact", "nope"))), [])
        self.assertContains(self.response, NOTE)
        self.assertContains(self.response, "admin-ext-choice-clear")

    def test_an_unreadable_key_beside_a_readable_one_only_drops_itself(self):
        found = self.names(
            url(DEVICES, ("tags__id__exact", "nope"), ("tags__id__exact", self.beta.pk))
        )
        self.assertEqual(found, ["one", "two"])
        self.assertContains(self.response, NOTE)

    def test_an_unknown_choice_matches_nothing(self):
        self.assertEqual(self.names(url(DEVICES, ("kind__exact", "bogus"))), [])
        self.assertContains(self.response, NOTE)

    def test_an_unknown_plain_value_matches_nothing(self):
        self.assertEqual(self.names(url(DEVICES, ("region", "nowhere"))), [])
        self.assertContains(self.response, NOTE)

    def test_an_unreadable_number_matches_nothing(self):
        self.assertEqual(self.sequences(url(READINGS, ("sequence", "abc"))), [])
        self.assertContains(self.response, NOTE)

    def test_isnull_false_does_not_widen_to_every_tagged_row(self):
        """Django would read it as 'not empty'; ORed with the rest that means everything."""
        self.assertEqual(self.names(url(DEVICES, ("tags__isnull", "false"))), [])
        self.assertContains(self.response, NOTE)

    def test_a_valid_request_shows_no_note(self):
        self.get(url(DEVICES, ("tags__id__exact", self.beta.pk)))
        self.assertNotContains(self.response, NOTE)


class ConfigurationTests(ChoiceFilterTestCase):
    def test_a_date_column_is_refused(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "cannot filter Reading.recorded_on"):
            build_filter(ChoiceFilter, self.reading_admin, "recorded_on")

    def test_a_boolean_column_is_refused(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "not BooleanField"):
            build_filter(MultipleChoiceFilter, self.device_admin, "archived")

    def test_a_json_column_is_refused(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "not JSONField"):
            build_filter(MultipleChoiceFilter, self.device_admin, "config")

    def test_the_parameters_are_djangos_own(self):
        cases = [
            (ChoiceFilter, self.device_admin, "kind", ["kind__exact"]),
            (MultipleChoiceFilter, self.device_admin, "tags", ["tags__id__exact", "tags__isnull"]),
            (MultipleChoiceFilter, self.device_admin, "region", ["region", "region__isnull"]),
            (ChoiceFilter, self.reading_admin, "device", ["device__id__exact"]),
        ]
        for filter_class, model_admin, field_path, expected in cases:
            with self.subTest(field_path=field_path):
                spec = build_filter(filter_class, model_admin, field_path)
                self.assertEqual(spec.expected_parameters(), expected)

    def test_a_relation_is_titled_like_djangos_own_filter(self):
        self.assertEqual(build_filter(MultipleChoiceFilter, self.reading_admin, "tag").title, "tag")

    def test_blank_values_are_not_offered(self):
        """ "" is the dropdown's own "All"; Django's EmptyFieldListFilter covers blanks."""
        Device.objects.create(name="blank", region="")
        spec = build_filter(MultipleChoiceFilter, self.device_admin, "region")
        self.assertNotIn("", [value for value, _ in spec.options])

    def test_plain_options_come_from_the_admins_own_queryset(self):
        Device.objects.create(name="secret", region="mars", archived=True)
        spec = build_filter(MultipleChoiceFilter, self.device_admin, "region")
        self.assertNotIn("mars", [value for value, _ in spec.options])


class MarkupTests(ChoiceFilterTestCase):
    def test_the_filter_uses_the_stock_sidebar_shell(self):
        self.get(DEVICES)
        self.assertContains(self.response, '<details data-filter-title="tags" open>')
        self.assertContains(self.response, "By tags")

    def test_both_are_get_forms_with_a_submit_button(self):
        self.get(DEVICES)
        self.assertContains(
            self.response, '<form class="admin-ext-choice" method="get" action=""', count=3
        )
        self.assertContains(
            self.response, '<select class="admin-ext-choice-select" name="kind__exact"'
        )
        self.assertContains(self.response, 'class="admin-ext-choice-apply"', count=3)

    def test_the_assets_ship_with_the_filter(self):
        self.get(DEVICES)
        self.assertContains(self.response, "django_extensions_admin/filters.css")
        self.assertContains(self.response, "django_extensions_admin/choice-filters.js")

    def test_search_is_offered_only_above_the_threshold(self):
        """Tags asks for it above two options; regions keep the default of ten."""
        self.get(DEVICES)
        self.assertContains(self.response, "data-admin-ext-choice-search=", count=1)
        self.assertIn("data-admin-ext-choice-search=", self.section("tags"))

    def test_facets_count_each_option(self):
        self.get(url(DEVICES, ("_facets", "True")))
        self.assertContains(self.response, "Gateway (1)")
        self.assertContains(self.response, "beta (2)")
        self.assertContains(self.response, "- (1)")
