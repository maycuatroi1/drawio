# Unreleased

- Route connectors exactly as draw.io does: `drawio/routing.py` ports mxGraph's
  OrthConnector, SegmentConnector, elbow connectors and perimeters (Apache-2.0). Native
  renders and lint now follow the editor for unpinned orthogonal connectors and for
  waypoints that are off the line of a port; tests compare against routes recorded from
  draw.io.
- Lint: `edge-hidden` for connectors painted under an opaque shape created after them;
  `style-ignored` (info) for properties draw.io ignores, such as `ellipse=1`; text boxes
  collide by their glyphs, not their line boxes; `--select`, `--ignore` and `-v`.
- Labels collapse runs of spaces as draw.io does.

- Render pages to PNG, SVG, PDF and JPEG on any OS: a built-in native renderer (SVG
  with no dependencies, raster through Pillow), the draw.io desktop exporter, or the
  official diagrams.net viewer in a headless browser.
- Add layout checks (`drawio lint`): overflowing text, overlaps, connectors through
  shapes or labels, children outside containers, small text and aspect ratio for a
  target size.
- Add automatic layout (`drawio.layout`: layered, row, column, grid), `page.fit()`,
  `page.autosize()`, text metrics, named shapes, images, colour presets,
  `Theme.drawio()`, arrow ends, absolute coordinates, cell geometry accessors,
  `page.remove()`, `page.find()`, `Document.import_page()` and `remove_page()`.
- New CLI commands for agents, all with `--json`: render, lint, inspect, fit, layout,
  merge, shapes, doctor and skill; ship an agent skill installable with
  `drawio skill install`.
- Fix `save()` creating files with mode 0600; explain duplicate-ID clashes with
  generated IDs.
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
