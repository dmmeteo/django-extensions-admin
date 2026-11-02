# Branding

Installed with the `branding` extra; see [installation](installation.md).

A logo and a few brand colours on the stock admin. It is not a theme. The layout, markup,
widgets, fonts and the light, dark and auto switching stay Django's. Nothing changes until your
own `admin/base_site.html` extends the package's template.

```django
{# templates/admin/base_site.html - any template directory ahead of django.contrib.admin #}
{% extends "django_extensions_admin/branding/base_site.html" %}
```

```python
# settings.py
ADMIN_EXTENSIONS = {
    "BRANDING": {
        "LOGO": "acme/admin-logo.svg",  # a static file path; optional
        "COLORS": {"secondary": "#1d4e44", "accent": "#f2c14e"},
    },
}
```

The header text is still `AdminSite.site_header`, `site_title` and `index_title`. Set those as
usual. Each `AdminSite` keeps its own text, and all of them share the one branding.

## What it changes

Two blocks of Django's own templates are extended, and both keep `{{ block.super }}`:
- `dark-mode-vars` gains one `<style>` that sets Django's documented admin colour variables.
  It sits after Django's variables and before `extrastyle`.
- `branding` gains an `<img>` before the stock `#site-name`. It is 32 px high, at most 40% of
  the viewport wide, not a link and not a tab stop. It is decorative (`alt=""`): the
  stock site name right beside it is the header's accessible name, so screen readers do not
  hear it twice and a logo that fails to load shows nothing. Set `LOGO_ALT` only when the
  logo carries information the header text does not.

Every package feature already reads these variables, so buttons, filters, the JSON editor
and the command pages follow the palette. Nothing else is restyled.

## Colours

`COLORS` and `DARK_COLORS` take Django's own variable names, without the leading `--`, and
hex values (`#rgb` or `#rrggbb`). Only the brand surfaces can be set:

| Variable | Used by the stock admin for |
| --- | --- |
| `secondary` | header background, buttons, selected links |
| `accent` | the site name |
| `header-bg`, `header-color`, `header-link-color` | the header, if it should differ from `secondary` |
| `primary` | module captions (and, in dark mode, breadcrumbs) |
| `breadcrumbs-bg` | the breadcrumbs bar |
| `link-fg`, `link-hover-color` | links |
| `button-hover-bg`, `default-button-bg` | hovered buttons and the Save button |

Body, background, border, message, error and font variables are deliberately not on the
list. The themes follow Django's own rules:
- Django gives `primary`, `breadcrumbs-bg`, `link-fg` and `link-hover-color` dark values of
  its own. A `COLORS` value for one of them is used in the light theme only. Dark mode keeps
  Django's value unless `DARK_COLORS` sets one.
- Every other `COLORS` value is used in both themes, as Django uses its own.
- Nothing is derived or computed. Choose values with enough contrast in both themes; the
  demo's palette is checked for 4.5:1 in the browser gate.

Invalid names and values are left out of the page and reported by system checks
(`django_extensions_admin.E201`-`E207`). A logo the static finders cannot see is a warning
(`W201`). A remote URL or `data:` URI is not used.

## Your own CSS and templates

Your `admin/base_site.html` is still an ordinary override. Add your stylesheet after the
branding layer, in `extrastyle`:

```django
{% extends "django_extensions_admin/branding/base_site.html" %}
{% load static %}
{% block extrastyle %}{{ block.super }}<link rel="stylesheet" href="{% static "acme/admin.css" %}">{% endblock %}
```

Use the selectors Django uses: `html[data-theme="light"], :root` for both themes, and
`html[data-theme="dark"]` plus `@media (prefers-color-scheme: dark) { :root { ... } }` for
dark. At the same specificity, your later rule wins. Other blocks (`branding`, `userlinks`,
`footer` and so on) can be overridden as in any Django project. Call `{{ block.super }}` in
`branding` and `dark-mode-vars` if you want to keep the logo and the palette.

On Django 6.0, with `ContentSecurityPolicyMiddleware` and the
`django.template.context_processors.csp` context processor, the `<style>` carries the
request's nonce. Add `CSP.NONCE` to `style-src`. On 5.2 there is no nonce, so a strict
`style-src` needs to allow the element some other way, or leave `COLORS` empty.

## When parts of it are missing

- No logo, or a logo that fails to load: the header text is there as before.
- No `branding.css`: the logo keeps its `height` attribute.
- No colours: no `<style>` is rendered.
- `"BRANDING": {}` renders exactly the stock page.

## Limitations

- **Where it is tested.** Only on the stock Django 5.2 and 6.0 admin, in Chromium. Admin skins that
  ship their own `admin/base.html` or `base_site.html` are not supported, and neither is a
  third-party stylesheet that redefines the same variables.
- **Scope.** One branding per project: every `AdminSite` gets the same logo and colours.
- **What it leaves to you.** There are no fonts, layout options, presets, per-user themes or
  free-form CSS. Contrast is the project's choice of values; nothing is checked at runtime.

## Removing branding

Delete your `admin/base_site.html`, or its `extends` line, and the stock admin is back. Then
remove `BRANDING` and the logo file. There is no data and no migration.
