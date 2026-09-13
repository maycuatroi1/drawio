# Contributing

## Local setup

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
make lint
make test
make build
```

Core XML generation must work with only the Python standard library. Keep
optional browser, PDF and spreadsheet dependencies out of the import path for
`Document`, `Graph` and `Node`.

## Changes and tests

Add tests for XML structure and failure cases. For layout changes, also open a
generated example in draw.io and inspect labels and connectors. XML validity
does not prove a readable layout.

Tests run in temporary working directories. Do not install packages, launch
browsers or contact external services inside a test. Use subprocess tests to
check the installed CLI and optional-dependency isolation.

Preserve `Graph`, `Node`, the `>>` DSL and the existing import paths. If behavior
must change, document it in the README and HISTORY.md. For the native builder,
prefer explicit IDs and parent-relative geometry over inferred layout.

Run `make fmt` to apply Ruff's import sorting and formatting. `make test` reports
coverage, including legacy modules that the native suite does not exercise.
Install `.[docs]` and run `make docs` to check the documentation.

## Release boundary

This change does not publish a package or bump the version. The existing
version-bump and release workflows remain configured separately. A maintainer
should review those workflows before pushing to `main` or creating a release
tag, since those actions can trigger versioning or publication.
