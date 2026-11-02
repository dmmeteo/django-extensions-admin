# Environment indicator

A thin accent line and a small readable badge with the environment's name on every admin page,
including the login page, so nobody edits production thinking it is staging. It needs no models,
migrations, JavaScript or network calls, and works with or without the other features.

```bash
pip install "django-extensions-admin[environment]"     # not on PyPI yet, see installation.md
```

```python
INSTALLED_APPS = [
    "django_extensions_admin.environment",   # before django.contrib.admin
    "django.contrib.admin",
    ...
]
ADMIN_EXTENSIONS = {"ENVIRONMENT": os.environ.get("ADMIN_ENVIRONMENT", "")}
```

An empty name shows nothing, so the same settings file can run everywhere and each deployment sets
its own name. The defaults are a 5 px line in the admin's own error red at the top, with the name in
a badge that hangs from it. A dict overrides them:

```python
ADMIN_EXTENSIONS = {
    "ENVIRONMENT": {
        "NAME": "Production",
        "COLOR": "#ba2121",     # #rgb or #rrggbb; the badge text is black or white, whichever reads better
        "POSITION": "top",      # or "bottom": the line is fixed to the bottom of the window
        "HEIGHT": 5,            # pixels, 2 to 12
    }
}
```

## What is enforced

- The name is ordinary template text: escaped, and cut to 40 characters.
- Only a validated hex colour, `top` or `bottom` and an integer height reach the page. Anything else
  falls back to the default and is reported by system checks `django_extensions_admin.E301` to `E306`;
  the name still shows, because hiding the indicator would hide the warning.
- The colours go into one `<style>` element that takes Django 6.0's `csp_nonce` when the CSP
  middleware provides one, plus a static stylesheet. There are no inline `style` attributes.
- Django's header is not changed: a top indicator sits above it and moves it down by the line's
  height, and the badge overlaps the header's empty middle. Nothing is shown in print or popups.

## Removing it

Remove the setting and `django_extensions_admin.environment` from `INSTALLED_APPS`, then
`pip uninstall django-extensions-admin-environment`. Setting the name to `""` is the quick off switch.
