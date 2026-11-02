# Tools panel

One resizable side panel that admin tools open in. Today its only tool is the [REPL](repl.md); it
exists so that later tools share one place, one button and one set of layout rules instead of each
bringing its own drawer. It is installed by the tools that use it (`django-extensions-admin[repl]`)
and does nothing on its own.

## What you see

- An icon button beside Django's theme toggle in the header, shown only to a user at least one tool is
  available to. Its accessible name and tooltip are "Tools panel"; the icon is a window with a side
  column, mirrored when the panel docks left. <kbd>Ctrl</kbd>+<kbd>`</kbd> toggles it too.
- The panel docks to the **right** by default, or the left with `ADMIN_EXTENSIONS["PANEL_SIDE"] = "left"`.
- Django's header keeps its full width, height, wrapping and position. The panel starts at the header's
  bottom edge and only the page below the header (breadcrumbs, content, footer) makes room. When you
  scroll the header away, the panel reaches the top of the window.
- Tabs at the top list the tools available to you. A tool that is not enabled, or not allowed for you,
  has no tab.
- Drag the panel's inner edge, or Tab to it and use the arrow keys (<kbd>Shift</kbd> for larger
  steps), <kbd>Home</kbd> and <kbd>End</kbd>. The width is clamped between 360 px and the window
  width minus 400 px, kept in the browser's local storage, and restored on every page. **Full width**
  covers the whole page below the header; **Close** hides the panel and keeps the tool's state.
- Below 760 px the panel overlays the page below the header instead of docking. It stays resizable by
  drag, touch and keys between 240 px and the window width minus 32 px, so the handle and a strip of
  page stay on screen; it opens at its widest unless you chose a width.
- No new theme: it uses the admin's own colour variables, so light, dark and auto follow Django.

## Settings

| Key | Default | Meaning |
| --- | --- | --- |
| `PANEL_SIDE` | `"right"` | `"right"` or `"left"`. Anything else is system check `django_extensions_admin.E401`. |

`django_extensions_admin.panel` goes in `INSTALLED_APPS` before `django.contrib.admin`: it adds its
button and markup through a layer of `admin/base_site.html` that keeps every `block.super`. Your own
`admin/base_site.html` keeps working as long as it extends `admin/base_site.html` (as the branding
adoption does) rather than `admin/base.html`.

## For tool authors

A tool is a Django app that registers a `django_extensions_admin.panel.Tool` in its
`AppConfig.ready()`: a key, a tab label, a template, `available(request)` and its static files. The
panel dispatches `admin-ext-panel:show` and `admin-ext-panel:hide` on `#admin-ext-panel`; a tool follows
its own element's size with a `ResizeObserver`. `available()` only decides what is rendered. Every view
a tool serves must check permissions itself.

## Removing it

Uninstall the tools that use it, remove `django_extensions_admin.panel` from `INSTALLED_APPS` and
`pip uninstall django-extensions-admin-panel`. It stores nothing on the server; the width and open
state live in each browser.
