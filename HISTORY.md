# Unreleased

- Add a standard-library XML API for documents, pages, nested containers,
  editable shapes, port anchors and connector waypoints.
- Load existing uncompressed/compressed diagrams and append pages while retaining
  existing XML and metadata.
- Render legacy Graph output to `.drawio` / `.xml` without Selenium; retain CSV,
  text, optional PDF export and explicit browser helpers.
- Fix graph edge identity, child registration, repeated CSV output and CSV quoting.
- Preserve labels and circular nodes in the basic Mermaid importer; reject
  unsupported syntax instead of silently dropping edges.
- Add an offline CLI, native examples, tests and a Python/OS CI matrix.

Changelog
=========


0.1.2 (2021-08-14)
------------------
- Fix release, README and windows CI. [Bruno Rocha]
- Release: version 0.1.0. [Bruno Rocha]


0.1.0 (2021-08-14)
------------------
- Add release command. [Bruno Rocha]
