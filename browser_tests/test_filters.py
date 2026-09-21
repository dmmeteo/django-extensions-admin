"""Range filters in a real browser. Each filter is its own GET form inside the stock
sidebar, so what matters here is that submitting one keeps the rest of the changelist."""

import datetime

from demoapp.models import Device, Reading
from django.utils import formats, timezone

from .base import BrowserTestCase

READINGS = "/admin/demoapp/reading/"
DEVICES = "/admin/demoapp/device/"

FROM_DATE = "#id_recorded_on__range__gte"
TO_DATE = "#id_recorded_on__range__lte"
FROM_VALUE = "#id_value__range__gte"
TO_VALUE = "#id_value__range__lte"


class RangeFilterBrowserTests(BrowserTestCase):
    def open(self, path, query="", **context_kwargs):
        page = self.new_page(**context_kwargs)
        self.login(page)
        page.goto(f"{self.live_server_url}{path}{query}")
        return page

    def open_list(self, path, query="", **context_kwargs):
        page = self.open(path, query, **context_kwargs)
        page.wait_for_selector("#result_list")
        return page

    def apply(self, page, field):
        """Submit the form that owns `field`: a range filter owns its two inputs only."""
        page.locator(f"form.admin-ext-range:has({field}) .admin-ext-range-apply").click()
        page.wait_for_load_state()

    def row_count(self, page):
        return page.locator("#result_list tbody tr").count()

    def test_a_date_range_and_a_numeric_range_narrow_the_list_together(self):
        """Two filters, two forms, one query string: the second carries the first."""
        today = timezone.localdate()
        start, end = today - datetime.timedelta(days=6), today - datetime.timedelta(days=2)
        expected = Reading.objects.filter(
            recorded_on__gte=start, recorded_on__lte=end, value__gte=20, value__lte=80
        ).count()
        self.assertGreater(expected, 0, "the seed should leave something inside the range")

        page = self.open_list(READINGS)
        page.fill(FROM_DATE, start.isoformat())
        page.fill(TO_DATE, end.isoformat())
        self.apply(page, FROM_DATE)
        page.fill(FROM_VALUE, "20")
        page.fill(TO_VALUE, "80")
        self.apply(page, FROM_VALUE)

        self.assertIn("recorded_on__range__gte", page.url)
        self.assertIn("value__range__lte", page.url)
        self.assertEqual(self.row_count(page), expected)
        self.shot(page, "filters-changelist")

    def test_applying_a_range_keeps_the_search_term_and_the_ordering(self):
        """The hidden inputs are the whole mechanism; without them this drops both."""
        page = self.open_list(READINGS, "?q=13%3A20&o=-4")
        searched = self.row_count(page)
        self.assertGreater(searched, 0)

        page.fill(FROM_VALUE, "0")
        self.apply(page, FROM_VALUE)

        self.assertIn("q=13%3A20", page.url)
        self.assertIn("o=-4", page.url)
        self.assertEqual(page.input_value("#searchbar"), "13:20")
        self.assertEqual(self.row_count(page), searched)

    def test_clearing_the_range_leaves_the_rest_of_the_query_alone(self):
        page = self.open_list(READINGS, "?q=13%3A20&value__range__gte=50")
        page.locator(".admin-ext-range-clear").first.click()
        page.wait_for_selector("#result_list")

        self.assertIn("q=13%3A20", page.url)
        self.assertNotIn("value__range__gte", page.url)

    def test_an_unreadable_bound_shows_the_reason_instead_of_a_result(self):
        """Typed straight into the URL: the sidebar explains it and the list is empty."""
        page = self.open(READINGS, "?value__range__gte=nope")
        page.wait_for_selector(".admin-ext-range-error")

        self.assertEqual(page.locator("#result_list").count(), 0)
        self.assertIn("Enter a number", page.locator(".admin-ext-range-error").first.inner_text())
        # The server hands the text back untouched; <input type="number"> then declines to
        # show something that is not a number, which is the browser's call, not ours.
        self.assertEqual(page.get_attribute(FROM_VALUE, "value"), "nope")
        self.assertEqual(page.input_value(FROM_VALUE), "")
        self.shot(page, "filters-bad-input")

    def test_the_form_still_works_without_its_stylesheet(self):
        """Without filters.css the inputs lose their fit, never their function."""
        page = self.new_page()
        page.route("**/django_extensions_admin/filters.css", lambda route: route.abort())
        self.login(page)
        page.goto(f"{self.live_server_url}{READINGS}")
        page.wait_for_selector("#result_list")

        page.fill(FROM_VALUE, "90")
        self.apply(page, FROM_VALUE)

        self.assertIn("value__range__gte=90", page.url)
        self.assertEqual(self.row_count(page), Reading.objects.filter(value__gte=90).count())
        self.shot(page, "filters-without-stylesheet")

    def test_the_range_filter_fits_a_narrow_dark_changelist(self):
        """The sidebar is the admin's own, so the inputs have to live inside its column."""
        page = self.open_list(DEVICES, color_scheme="dark", viewport={"width": 420, "height": 900})
        page.locator("#changelist-filter").scroll_into_view_if_needed()
        overflow = page.evaluate(
            """() => {
                const sidebar = document.querySelector('#changelist-filter');
                const edge = sidebar.getBoundingClientRect().right;
                const controls = sidebar.querySelectorAll(
                    '.admin-ext-range input, .admin-ext-range button');
                return Array.from(controls).map(
                    el => Math.round(el.getBoundingClientRect().right - edge));
            }"""
        )
        self.assertTrue(overflow, "the range filter should be in the sidebar")
        self.assertEqual([wider for wider in overflow if wider > 0], [])
        self.shot(page, "filters-narrow-dark")

    def test_a_date_range_over_an_instant_column_means_the_local_day(self):
        """The demo sights half its devices at 23:55 local, which is the next day in UTC.

        Django's own `__date` lookup converts in the active timezone too, so the two
        expressions of "sighted on this day" have to agree.
        """
        day = timezone.localdate() - datetime.timedelta(days=1)
        expected = Device.objects.filter(last_seen_at__date=day).count()
        self.assertGreater(expected, 0)

        page = self.open_list(
            DEVICES,
            f"?last_seen_at__range__gte={day.isoformat()}"
            f"&last_seen_at__range__lte={day.isoformat()}",
        )
        self.assertEqual(self.row_count(page), expected)
        for shown in page.locator("#result_list tbody tr .field-last_seen_at").all_inner_texts():
            self.assertIn(formats.date_format(day, "N j, Y"), shown)
