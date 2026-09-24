"""Choice filters in a real browser. Each one is a GET form in the stock sidebar, so what
matters is that the real controls produce the right query string - several values as a
repeated key - that the rest of the changelist survives, and that nothing needs the
script except the search box."""

from urllib.parse import parse_qs, urlsplit

from demoapp.models import Device, Reading, Tag

from .base import BrowserTestCase

DEVICES = "/admin/demoapp/device/"
READINGS = "/admin/demoapp/reading/"

REGION = 'select[name="region"]'
# By checkbox: every other filter's form carries these names too, as hidden inputs.
STATUS_FORM = 'form.admin-ext-choice:has(input[type="checkbox"][name="status"])'
TAGS_FORM = 'form.admin-ext-choice:has(input[type="checkbox"][name="tags__id__exact"])'
REGION_FORM = f"form.admin-ext-choice:has({REGION})"


def query(page):
    """The page's query string as {name: [values]}, repeated keys kept."""
    return parse_qs(urlsplit(page.url).query, keep_blank_values=True)


class ChoiceFilterBrowserTests(BrowserTestCase):
    def open_list(self, path, query_string="", **context_kwargs):
        page = self.new_page(**context_kwargs)
        self.login(page)
        page.goto(f"{self.live_server_url}{path}{query_string}")
        page.wait_for_selector("#result_list")
        return page

    def apply(self, page, form):
        page.locator(f"{form} .admin-ext-choice-apply").click()
        page.wait_for_selector("#result_list")

    def check(self, page, form, label):
        page.locator(f"{form} label", has_text=label).locator("input").check()

    def row_count(self, page):
        return page.locator("#result_list tbody tr").count()

    def test_one_region_from_the_dropdown(self):
        region = Device.objects.order_by("pk").first().region
        page = self.open_list(DEVICES)
        page.select_option(REGION, region)
        self.apply(page, REGION_FORM)

        self.assertEqual(query(page)["region"], [region])
        self.assertEqual(self.row_count(page), Device.objects.filter(region=region).count())
        self.assertEqual(page.input_value(REGION), region)

    def test_several_tags_are_ored_and_each_device_is_listed_once(self):
        """Two tags as two repeated keys; a device carrying both is still one row."""
        chosen = ["rack 4, bay 2", "r&d", "metrics"]
        expected = Device.objects.filter(tags__name__in=chosen).distinct().count()
        self.assertGreater(expected, 0)

        page = self.open_list(DEVICES)
        for name in chosen:
            self.check(page, TAGS_FORM, name)
        self.apply(page, TAGS_FORM)

        ids = sorted(
            str(pk) for pk in Tag.objects.filter(name__in=chosen).values_list("pk", flat=True)
        )
        self.assertEqual(sorted(query(page)["tags__id__exact"]), ids)
        self.assertEqual(self.row_count(page), expected)
        for name in chosen:
            box = page.locator(f"{TAGS_FORM} label", has_text=name).locator("input")
            self.assertTrue(box.is_checked())
        self.shot(page, "choice-filters-changelist")

    def test_a_value_with_a_comma_and_an_ampersand_is_one_value(self):
        page = self.open_list(DEVICES)
        self.check(page, STATUS_FORM, "on hold, r&d")
        self.check(page, STATUS_FORM, "idle")
        self.apply(page, STATUS_FORM)

        self.assertEqual(sorted(query(page)["status"]), ["idle", "on hold, r&d"])
        self.assertEqual(
            self.row_count(page), Device.objects.filter(status__in=["idle", "on hold, r&d"]).count()
        )

    def test_applying_keeps_the_search_ordering_and_other_filters(self):
        device = Device.objects.filter(archived=False).order_by("pk").first()
        page = self.open_list(DEVICES, f"?q=device&o=-1&archived__exact=0&region={device.region}")
        self.check(page, STATUS_FORM, device.status)
        self.apply(page, STATUS_FORM)

        params = query(page)
        self.assertEqual(params["q"], ["device"])
        self.assertEqual(params["o"], ["-1"])
        self.assertEqual(params["archived__exact"], ["0"])
        self.assertEqual(params["region"], [device.region])
        self.assertEqual(params["status"], [device.status])
        self.assertEqual(page.input_value("#searchbar"), "device")
        self.assertEqual(
            self.row_count(page),
            Device.objects.filter(
                name__icontains="device",
                archived=False,
                region=device.region,
                status=device.status,
            ).count(),
        )

    def test_clear_removes_only_that_filter(self):
        tag = Tag.objects.get(name="metrics")
        page = self.open_list(
            DEVICES, f"?q=device&tags__id__exact={tag.pk}&tags__isnull=True&status=idle"
        )
        page.locator(f"{TAGS_FORM} .admin-ext-choice-clear").click()
        page.wait_for_selector("#result_list")

        params = query(page)
        self.assertNotIn("tags__id__exact", params)
        self.assertNotIn("tags__isnull", params)
        self.assertEqual(params["q"], ["device"])
        self.assertEqual(params["status"], ["idle"])

    def test_both_filters_work_without_javascript(self):
        """No script: no search box, and the forms still submit what was chosen."""
        page = self.open_list(DEVICES, java_script_enabled=False)
        self.assertEqual(page.locator(".admin-ext-choice-search").count(), 0)

        page.select_option(REGION, "us-east")
        self.apply(page, REGION_FORM)
        self.check(page, STATUS_FORM, "idle")
        self.check(page, STATUS_FORM, "running")
        self.apply(page, STATUS_FORM)

        params = query(page)
        self.assertEqual(params["region"], ["us-east"])
        self.assertEqual(sorted(params["status"]), ["idle", "running"])
        self.assertEqual(
            self.row_count(page),
            Device.objects.filter(region="us-east", status__in=["idle", "running"]).count(),
        )
        self.shot(page, "choice-filters-no-js")

    def test_search_narrows_the_options_but_not_the_selection(self):
        """A checked box filtered out of view is still submitted."""
        page = self.open_list(DEVICES)
        search = page.locator(f"{TAGS_FORM} .admin-ext-choice-search")
        self.assertEqual(page.locator(".admin-ext-choice-search").count(), 1, "only tags is long")

        self.check(page, TAGS_FORM, "solar")
        search.fill("RACK")
        visible = page.locator(f"{TAGS_FORM} .admin-ext-choice-options li:visible")
        self.assertEqual([text.strip() for text in visible.all_inner_texts()], ["rack 4, bay 2"])
        self.shot(page, "choice-filters-search")

        search.press("Enter")  # searches; must not submit a half-made selection
        self.assertNotIn("tags__id__exact", page.url)

        search.fill("zzz")
        self.assertTrue(page.locator(f"{TAGS_FORM} .admin-ext-choice-nomatch").is_visible())
        search.fill("rack")
        self.check(page, TAGS_FORM, "rack 4, bay 2")
        self.apply(page, TAGS_FORM)

        names = Tag.objects.filter(pk__in=query(page)["tags__id__exact"]).values_list(
            "name", flat=True
        )
        self.assertEqual(sorted(names), ["rack 4, bay 2", "solar"])

    def test_search_over_a_long_dropdown(self):
        """Twelve devices: the dropdown gets a box, and "All" is never searched away."""
        page = self.open_list(READINGS)
        form = 'form.admin-ext-choice:has(select[name="device__id__exact"])'
        page.locator(f"{form} .admin-ext-choice-search").fill("device-1")
        shown = page.evaluate(
            """form => Array.from(document.querySelector(form).querySelectorAll('option'))
                .filter(option => option.style.display !== 'none')
                .map(option => option.textContent)""",
            form,
        )
        self.assertEqual(shown, ["All", "device-10", "device-11", "device-12"])

        page.select_option(f"{form} select", label="device-11")
        self.apply(page, form)
        device = Device.objects.get(name="device-11")
        self.assertEqual(
            self.row_count(page), min(Reading.objects.filter(device=device).count(), 100)
        )

    def test_the_choice_filters_fit_a_narrow_dark_changelist(self):
        page = self.open_list(DEVICES, color_scheme="dark", viewport={"width": 420, "height": 900})
        page.locator("#changelist-filter").scroll_into_view_if_needed()
        overflow = page.evaluate(
            """() => {
                const sidebar = document.querySelector('#changelist-filter');
                const edge = sidebar.getBoundingClientRect().right;
                const controls = sidebar.querySelectorAll(
                    '.admin-ext-choice select, .admin-ext-choice input:not([type=hidden]),'
                    + ' .admin-ext-choice button, .admin-ext-choice label');
                return Array.from(controls).map(
                    el => Math.round(el.getBoundingClientRect().right - edge));
            }"""
        )
        self.assertTrue(overflow, "the choice filters should be in the sidebar")
        self.assertEqual([wider for wider in overflow if wider > 0], [])
        # The admin's dark palette reaches the select: it is not left light on dark.
        background = page.evaluate(
            "() => getComputedStyle(document.querySelector('select[name=region]')).backgroundColor"
        )
        self.assertNotEqual(background, "rgb(255, 255, 255)")
        self.shot(page, "choice-filters-narrow-dark")
