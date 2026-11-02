# List filters

Installed with the `filters` extra; see [installation](installation.md).

Two independent sets of `list_filter` classes. Neither is registered globally, so a field gets one
only where you list it, and neither needs a mixin, a setting, a custom `AdminSite` or a template of
your own.

## Range filters

Inclusive from and to bounds for a date, datetime or numeric column, as an ordinary
`list_filter` entry.

```python
from django.contrib import admin
from django_extensions_admin import DateRangeFilter, DateTimeRangeFilter, NumericRangeFilter

@admin.register(Reading)
class ReadingAdmin(admin.ModelAdmin):
    list_filter = [
        ("recorded_on", DateRangeFilter),
        ("recorded_at", DateTimeRangeFilter),
        ("value", NumericRangeFilter),
        "device",
    ]
```

The sidebar gets two native inputs and an **Apply** button, with no JavaScript.

| Filter | Field types | Input | Query parameters |
| --- | --- | --- | --- |
| `DateRangeFilter` | `DateField`, `DateTimeField` | `<input type="date">` | `<field>__range__gte`, `<field>__range__lte` |
| `DateTimeRangeFilter` | `DateTimeField` | `<input type="datetime-local">` | the same two |
| `NumericRangeFilter` | `IntegerField`, `FloatField`, `DecimalField` | `<input type="number">` | the same two |

Both parameters are optional: one bound alone is a one-sided range, not an error. They are
declared as the filter's expected parameters, so the changelist hands them to the filter
instead of treating them as raw ORM lookups. Attaching a filter to a field type it cannot
read raises `ImproperlyConfigured` at the point the changelist builds its filters, naming
the class and the field.

### What the bounds mean

- **A `DateField`** is filtered with `__gte` and `__lte` on the dates themselves. Both ends
  are included.
- **A `DateTimeField` under `DateRangeFilter`** means whole days: `__gte` at midnight
  starting the first day and `__lt` at midnight after the last. The range is open at the top on
  purpose. An inclusive `__lte` would have to name a last instant, and would then drop whatever
  a column with more precision than that instant still holds.
- **`DateTimeRangeFilter`** includes both instants, to the minute the browser offers.
- **`NumericRangeFilter`** includes both numbers, parsed by the model field's own form
  field. A `DecimalField` therefore brings its own precision and the matching input step,
  and an `IntegerField` its column's range.

**Timezone.** Every date-like bound is read in Django's *active* timezone, so "the 3rd"
means the reader's 3rd, not UTC's. Parsing is Django's own `forms.DateField` /
`forms.DateTimeField`, which already route through `from_current_timezone()`; the whole-day
boundaries use `timezone.make_aware()`. With `USE_TZ = False` the bounds stay naive, like
the column. A `datetime-local` input has no timezone picker, so the time you type is a
local wall-clock time, not an offset.

### When input is wrong

None of these raises, and none of them widens the result. The filter runs on the queryset
your `ModelAdmin` already authorized, so it can only take rows away from it.

| Input | What happens |
| --- | --- |
| Neither bound | No filtering. The form still renders. |
| One bound only | A one-sided range. Supported, not an error. |
| A bound the field cannot read | The error is shown under that input, and the list is empty. |
| Start after end | "The start of the range is after its end." under the form, and the list is empty. |

An empty list is the point: a bound nobody can read must not quietly behave like no filter
at all. The text you typed is handed straight back in the HTML, though a browser's
`<input type="number">` will decline to *display* something that is not a number.

Submitting the form is an ordinary GET. It carries the rest of the query string (the
search term, the ordering, the other filters) as hidden inputs, and drops the page number,
because a new range starts at page one. **Clear** removes that filter's own two parameters
and nothing else. Each range filter is its own form, so applying two of them is two
submits; the second carries the first.

### Limitations

- Two bounds on one field. No saved presets, no relative shortcuts ("last 7 days" is Django's own
  `DateFieldListFilter`), no `__in` lists and no query builder.
- No facet counts. Django's counts are per choice, and a range is not a list of choices;
  `show_facets` still works for every other filter on the page.
- `<input type="date">` and `<input type="datetime-local">` are the browser's own controls. Their
  displayed format follows the browser's locale rather than Django's, and a browser without them
  falls back to a text field that wants `YYYY-MM-DD`.

### Removing range filters

Delete the `list_filter` entry and the import. There is no model field, no migration, no
stored state and no data format of ours anywhere. Bookmarked URLs stop filtering.
Django's own `DateFieldListFilter` and `admin.EmptyFieldListFilter` are drop-in
replacements for part of it if you want to keep something.

## Choice filters

A compact dropdown for one value, or a checkbox list for several values of the same field,
ORed together. Both are ordinary `list_filter` entries.

```python
from django.contrib import admin
from django_extensions_admin import ChoiceFilter, MultipleChoiceFilter

@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_filter = [
        ("region", ChoiceFilter),          # one value, from a <select>
        ("status", MultipleChoiceFilter),  # any of several values
        ("tags", MultipleChoiceFilter),    # works across many-to-many, one row per device
        "archived",
    ]
```

Selecting two tags lists the devices that carry either one. Values of *different* fields
still narrow each other, as every other filter does.

| Field | Options | Query parameter |
| --- | --- | --- |
| `ForeignKey`, `OneToOneField`, `ManyToManyField`, reverse relations | the related objects, in the related admin's ordering | `<field>__<pk>__exact`, plus `<field>__isnull` for the empty choice |
| Any field with `choices` | the field's choices | `<field>__exact`, plus `<field>__isnull` when `None` is a choice |
| `CharField`, `IntegerField`, `DecimalField`, `UUIDField` without choices | the distinct values in the admin's own queryset | `<field>`, plus `<field>__isnull` when a row is `NULL` |

These are Django's own parameter names, the ones its default filter for that field uses.
Several values arrive as a repeated key, `?status=idle&status=running`. Values are never
joined into one comma-separated string, so a value containing a comma, `&`, `%` or quotes
stays one value. A path through a relation (`"device__region"`) works the same way. Any
other field type (dates, booleans, JSON, text, floats) raises `ImproperlyConfigured` when
the changelist builds its filters, naming the class and the field. Dates have the range
filters, and booleans are already compact in Django's default filter.

Each filter is a GET form with an **Apply** button, in the stock sidebar markup. The
checkbox list is the stock `<ul>`, and a selected row gets the stock `selected` marker. The
form carries the rest of the query string (search, ordering, other filters) and drops the
page number. **Clear** removes exactly that filter's own parameters. It leaves alone a
range filter on the same column (`sequence` vs `sequence__range__gte`). With `show_facets`,
each option shows its count.

### Search over long lists

A filter with more than 10 options gets a search box above them. It hides the options that
don't match; the selection itself doesn't change, so a checked box you've searched out of
view is still submitted. It is a small vanilla script, `choice-filters.js`, and it only
searches options already on the page: no request, no autocomplete endpoint. Without
JavaScript there's no search box, and both filters work exactly the same. To change the
threshold, subclass:

```python
class TagFilter(MultipleChoiceFilter):
    search_threshold = 0  # always offer search
```

### What each filter reads

- **`MultipleChoiceFilter`** reads every value of its parameter and ORs them. It also
  offers the field's empty choice, shown with the admin's empty-value display (or the label
  of a `None` choice), as one more box.
- **`ChoiceFilter`** reads one value. When the URL repeats the key, it uses the last one,
  which is the one the dropdown can show. It has no empty choice: a `<select>` sends one
  parameter, and "empty" is a different parameter in Django. Use `MultipleChoiceFilter` or
  Django's `admin.EmptyFieldListFilter` for that.
- An empty value is the dropdown's own **All**, so blank strings are not offered as an
  option in either filter. `admin.EmptyFieldListFilter` covers them.

### Values it cannot offer

None of these raises or redirects, and none of them widens the result. The filter runs on
the queryset your `ModelAdmin` already authorized, so it can only take rows away.

| Input | What happens |
| --- | --- |
| A value the field cannot read (`?tags__id__exact=nope`) | Matches nothing. Alone, the list is empty. |
| An unreadable value next to readable ones | The readable ones still apply. The unreadable one adds no rows. |
| A readable value that is not an offered option | It is filtered exactly like any other value, which usually means no rows. |
| `<field>__isnull` with anything but `True`/`1` | Matches nothing. It doesn't mean "not empty", which ORed with the rest would mean nearly everything. |

In every one of these cases the sidebar says "A selected value is not one of the choices."
and shows **Clear**, so the widget never claims "All" while the list is filtered.

### Limitations

- Choice filters pick values; they do not build queries. No AND mode within one field, no dependent
  filters, no remote autocomplete, and no "only values in use" variant for relations: every related
  object is offered, as in Django's `RelatedFieldListFilter`.
- Every option is rendered into the page. The search box keeps a long list usable, but thousands of
  related objects are still thousands of options. For that, use Django's
  `RelatedOnlyFieldListFilter` or search.
- Hiding `<option>`s during a search is honoured by Chromium, which the gate runs. Other browsers are
  untested and may show every option; the dropdown still works.

### Removing choice filters

Replace `("status", MultipleChoiceFilter)` with `"status"`. There is no model field, no
migration and no stored state. Bookmarked URLs keep working, because the parameter names are
Django's and Django also ORs a repeated key. The one exception is "empty" together with a
value, which Django's own filter reads as both at once and therefore matches nothing.
