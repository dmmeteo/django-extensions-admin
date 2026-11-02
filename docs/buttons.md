# Buttons

Installed with the `buttons` extra; see [installation](installation.md).

```python
from django.contrib import admin
from django_extensions_admin import admin as extensions_admin

@admin.register(Device)
class DeviceAdmin(extensions_admin.ButtonsMixin, admin.ModelAdmin):
    list_display = ("name", "region", "status")

    changelist_buttons = ["ping_all", "count_by_region", "purge"]
    changeform_buttons = ["run_diagnostics", "archive"]
    row_buttons = ["archive"]

    @extensions_admin.button(description="Ping all devices")
    def ping_all(self, request):
        return f"Pinged {self.get_queryset(request).update(status='pinged')} devices."

    @extensions_admin.button(description="Count by region", permissions=["view"])
    def count_by_region(self, request):
        return f"{self.get_queryset(request).count()} devices."

    @extensions_admin.button(description="Purge", permissions=["purge"], danger=True)
    def purge(self, request):
        deleted, _ = self.get_queryset(request).filter(archived=True).delete()
        return (f"Purged {deleted} rows.", "warning")

    def has_purge_permission(self, request):
        return request.user.has_perm("app.purge_device")

    @extensions_admin.button(description="Run diagnostics")
    def run_diagnostics(self, request, obj):
        return f"Diagnostics finished for {obj}."

    @extensions_admin.button(description="Archive", confirm="Archive this device?", danger=True)
    def archive(self, request, obj):
        obj.archived = True
        obj.save(update_fields=["archived"])
        return f"Archived {obj}."
```

`ModelAdmin`, `register` and everything else still come from `django.contrib.admin`.
`django_extensions_admin.admin` is a two-name namespace for this package's own API, not a
proxy for Django's. `from django_extensions_admin import ButtonsMixin, button` works too.

## Placement

| Option | Where | Handler |
| --- | --- | --- |
| `changelist_buttons` | the list toolbar | `(self, request)` |
| `changeform_buttons` | an existing object's change form | `(self, request, obj)` |
| `row_buttons` | every row of the list | `(self, request, obj)` |

The lists own placement **and order**. The decorator has no position flag. One object
handler can appear in both `changeform_buttons` and `row_buttons`: it is a single endpoint,
and it returns you to whichever page you used it from. Object buttons never appear on the
add form.

A changelist handler gets no queryset and no selection. Build what you need from
`self.get_queryset(request)`. For operations on *selected* rows, use an ordinary Django
action. Buttons are not a second bulk-action system and **never** appear in the action
dropdown.

Declaring a name that does not exist, is not decorated with `@button`, or has the wrong
handler shape for its list raises `ImproperlyConfigured` with the class, the list and the
reason. It never silently does the wrong thing.

## `button(...)`

| Argument | Default | Meaning |
| --- | --- | --- |
| `description` | the method name | The label, like `@admin.action(description=...)`. |
| `permissions` | `None` | Names checked as `ModelAdmin.has_<name>_permission`, exactly as `@admin.action(permissions=...)`: **any** one of them is enough. |
| `confirm` | `None` | `True` or a question. The handler only runs from a server-rendered confirmation page (works without JavaScript). |
| `danger` | `False` | Destructive styling only. It is not a permission. |

Return `None` (default message), a string, a `(message, "success"/"warning"/"error"/...)`
pair, or an `HttpResponse` to take over the response entirely.

## What is enforced

- **Permissions are Django's.** `has_module_permission` is always required. With no
  `permissions` a button is a change operation: `has_change_permission(request, obj)` for the
  object in question. Declaring `permissions` **replaces** that default with `any()` over
  `has_<name>_permission`, the same rule Django applies to actions. So
  `permissions=["purge"]` means "whatever `has_purge_permission` says", not "change *and*
  purge". Custom policy goes in a `has_<name>_permission` method on your ModelAdmin.
- **Checked at the endpoint, not just at render time.** Hiding a button is cosmetic;
  guessing its URL gets a 403.
- **Method safety.** Every button is POST-only: `405` on GET, covered by Django's CSRF
  middleware. A handler that only reads still POSTs, and may return an `HttpResponse`.
- **Object lookup** goes through `ModelAdmin.get_object()`, so a row outside
  `get_queryset(request)` is a 404, not a leak.
- **List state** survives: buttons carry `_changelist_filters`, and the redirect afterwards
  puts you back on the same filtered, sorted, paginated page.
- **Descriptions are escaped.** HTML in a description is shown, never run.

## Markup: why buttons are not wrapped in `<form>`

The changelist rows are rendered *inside* Django's own `#changelist-form`. A nested
`<form>` is invalid HTML and browsers drop it, so the buttons would quietly stop working.
Instead the mixin renders one empty `<form id="admin-ext-action-form">` outside that form,
and every button points at it with `form="admin-ext-action-form"` and `formaction="…"`.
This is valid HTML5, it is verified in a real browser, and it means a button submits
*only itself*: bulk actions and pending `list_editable` edits are left alone.

The mixin sets `change_list_template` / `change_form_template` to thin templates that
extend the stock admin ones. If your project already overrides those, make your own
template extend `django_extensions_admin/change_list.html` instead.

Row buttons get their own column, appended automatically. Put `"row_buttons_column"`
anywhere in `list_display` to place it yourself, set `row_buttons_column_label` to rename
it, or set `auto_row_buttons_column = False` to leave it out.

## Limitations

- Buttons are buttons. There is no workflow engine, no action-form builder, no chaining and no
  persisted run history.
- A long-running handler blocks the request. Hand the work to your own task runner, or register it
  as a command for the [command runner](commands.md).

## Removing buttons

Delete the three lists and the mixin. The decorated methods become ordinary methods; the
`@button` lines can go with them. No models, no migrations, no stored data.
