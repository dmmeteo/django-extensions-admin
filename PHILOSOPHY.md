# Project philosophy

**Ordinary Django, with repetitive work removed.**

Build the package people install in most projects because it stays out of the way and regularly helps — not a mega-package that contains everything.

This is accepted product direction for django-extensions-admin. It governs feature selection, planning, API design and review. It is our interpretation of the spirit of django-extensions, not that project's official manifesto. We are independent and unaffiliated.

## Principles

1. **A toolkit, not a framework.** Each utility is useful independently. Using the JSON widget must not require adopting buttons or a mandatory all-purpose ModelAdmin base class. Consistency comes from shared conventions, not forced coupling.
2. **Django-native first.** Build on ModelAdmin, forms, widgets, permissions, messages, URLs and templates. Preserve Django's contracts and conventions; extend its supported hooks rather than introduce competing semantics. The API should feel like something that could belong in Django itself, without claiming official status or eventual inclusion. Introduce a new concept only when existing Django primitives cannot express the need simply.
3. **One installation does not enable everything.** Capabilities are explicitly adopted. Installing the app must not expose a REPL, enable command execution or silently change every JSON field. Dangerous operations require server-side authorization; hidden buttons are not a security boundary.
4. **Dependencies follow features.** Keep the core small. Specialized integrations bring only their own optional dependencies. Adding a button must not install a terminal stack, task runner or frontend build toolchain.
5. **Small examples, little ceremony.** The simplest useful example should take a few understandable lines. Prefer sensible defaults and local overrides to elaborate configuration or a new DSL.
6. **Complement Django; be ready to step aside.** When Django provides a good native solution, use it. When a project no longer needs a utility, make leaving it straightforward. Design for removal as well as adoption: avoid proprietary data formats and unnecessary coupling, and document how to remove configuration, imports and integrations without losing application data. Retire redundant helpers through a documented compatibility/deprecation path rather than abruptly breaking existing users. Becoming unnecessary is a successful outcome, not a reason to invent more scope.
7. **Preserve the admin's identity.** Keep the stock layout, navigation, interaction patterns and light/dark conventions. Optional colours, logo and restrained polish are fine; a new theme or design system is not the product.

## Planning through this philosophy

Before proposing a feature, changing the roadmap, designing an API, implementing or reviewing a change, read this document. Add a short **Philosophy fit** section to the plan or task packet:

- **Need:** What recurring Django-admin pain does this remove? Why is the native solution insufficient?
- **Smallest API:** Show the smallest useful usage example using Django primitives.
- **Independence and cost:** What does adopting this utility require? What happens for projects that do not enable it?
- **Exit path:** How can a project remove this utility or replace it with native Django? Identify any data or migration implications; no silent loss or forced dependency on unrelated features.
- **Safety and familiarity:** Which permissions, explicit activation, data-preservation and stock-UI boundaries must hold?
- **Scope and proof:** What are we deliberately leaving out, and which checks will demonstrate the intended behavior?

Keep this proportional: a small fix needs a few lines, not a new specification. A roadmap item is a candidate, not an exception to these principles.

If a proposal conflicts with a principle, first simplify or defer it. If an exception is genuinely necessary, obtain an explicit product decision and record the reason here before implementation; do not silently reinterpret the philosophy to fit existing code.

At completion, reconcile intended behavior with implementation and evidence. Tests passing do not by themselves demonstrate that the feature belongs in this package.

## Inspiration

- [django-extensions](https://github.com/django-extensions/django-extensions): the collection-of-utilities approach.
- [Package metadata](https://github.com/django-extensions/django-extensions/blob/main/pyproject.toml): a small core dependency footprint.
- [Admin autocomplete deprecation](https://django-extensions.readthedocs.io/en/latest/admin_extensions.html): prefer Django's native replacement when it exists.

This document owns product principles, not current implementation status. See README for usage and limitations, ROADMAP for work candidates, and tests/reports for demonstrated behavior.
