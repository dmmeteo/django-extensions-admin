# Releasing

A short checklist so an upload ships what the gate proved, and nothing the README does not
claim. It is not a process beyond that.

## Before any upload

1. The release commit is on `main`, the tree is clean, and `bash scripts/verify.sh` ends with
   `GATE PASSED` on that exact commit. The gate builds both artifacts into `dist/`, checks
   their contents, runs `twine check --strict` and installs each one into a clean
   environment.
2. The version lives in one place: `__version__` in `src/django_extensions_admin/__init__.py`.
   `pyproject.toml` reads it from there.
3. PyPI shows the README from the upload. So the release commit switches README's
   "not yet published on PyPI" notes (the release-status note and **Install**) to
   `pip install django-extensions-admin`, and the gate is rerun after that edit. If the
   upload does not happen, revert that commit.
4. Upload exactly the two files in `dist/` from that gate run. Do not rebuild in between.

## Owner-only steps

These need the owner's PyPI and GitHub accounts, and nothing in this repository does them:

- A PyPI account with 2FA. The name `django-extensions-admin` is free as of 2026-09-26; the
  first successful upload claims it.
- Optionally, a dry run on TestPyPI first.
- The upload, with an API token or a trusted publisher the owner configures
  (`uv publish` or `twine upload dist/*`).
- Tag `v0.1.0` on the release commit and create the GitHub release.
- Afterwards, `pip install django-extensions-admin==0.1.0` into a fresh environment and
  check that `import django_extensions_admin` works.
