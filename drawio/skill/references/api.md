# drawio-python API reference

All coordinates are draw.io units (1 unit = 1 px at 100% zoom). Geometry of a child is
relative to its parent container; connector waypoints use page coordinates.

## Document

| Call | Result |
|---|---|
| `Document(theme=Theme())` | empty document; `Theme.drawio()` for the editor's look |
| `Document.load(path)`, `Document.from_xml(xml)` | read `.drawio`/`.xml`, compressed or not |
| `doc.add_page(name, id=None, width=1600, height=1000, background="#ffffff")` | new `Page` |
| `doc.pages`, `doc.get_page(id)` | pages in order; one page by ID |
| `doc.import_page(page, id=None, name=None)` | copy a page (from any document) to the end |
| `doc.remove_page(page_or_id)` | delete a page |
| `doc.validate(check_bounds=False)` | raise `ValueError` on broken IDs, references, hierarchy |
| `doc.save(path, overwrite=False)` | atomic write; refuses to replace unless `overwrite=True` |
| `doc.to_xml()`, `doc.to_url()` | XML string; diagrams.net editor link (no upload) |

## Theme

`Theme(font_family="Helvetica", font_size=18, fill_color="#ffffff", stroke_color="#8091a5",
text_color="#182b40", line_color="#6b7d91", stroke_width=1.5, edge_width=2,
end_arrow="block", spacing=10)`. `Theme.drawio(**overrides)`: Helvetica 12, black lines
and text, stroke width 1, classic arrows, spacing 2.

## Page: creating cells

| Call | Notes |
|---|---|
| `box(label, x, y, width=200, height=90, *, id, parent, style, html, shape, absolute, autosize)` | any vertex |
| `container(label, x, y, width, height, **box_kwargs)` | title at the top; children use `parent=` |
| `text(label, x, y, width=400, height=40, **box_kwargs)` | no fill, no outline, left aligned |
| `ellipse(label, x, y, width=120, height=80, **box_kwargs)` | same as `box(shape="ellipse")` |
| `image(source, x, y, width=64, height=64, *, label="", **box_kwargs)` | file (embedded), URL or data URI |
| `connect(source, target, label="", *, id, source_port, target_port, waypoints, dashed, style, arrow, start_arrow)` | orthogonal connector |

- `style` is a mapping of draw.io style properties (`fillColor`, `fontSize`, `fontStyle`
  (1 bold, 2 italic, 4 underline), `align`, `verticalAlign`, `rounded`, `dashed`, ...).
- Labels are plain text; `html=True` only for markup you trust.
- Ports are `(x, y)` fractions of the shape: `(1, 0.5)` is the middle of the right side.
- `arrow` / `start_arrow`: `none, block, classic, open, oval, diamond, blockThin,
  classicThin, openThin, ERone, ERmany, ERmandOne, ERoneToMany, ERzeroToOne,
  ERzeroToMany`; `arrow=None` means no arrow head.

## Page: reading and changing

| Call | Result |
|---|---|
| `page.cells`, `page.shapes`, `page.edges` | tuples of `Cell` |
| `page.get(id)`, `page.find(label)`, `page.children(parent=None)` | lookups |
| `page.bounds(cell)` | `(x, y, w, h)` in page coordinates |
| `page.remove(cell)` | delete with its children and attached connectors |
| `page.autosize(cell, max_width=None)` | grow a shape so its label fits |
| `page.fit(container=None, padding=20)` | grow one container, or all containers and the page |
| `page.validate(check_bounds=False)`, `page.to_xml()` | checks; `mxGraphModel` XML |

`Cell`: `id`, `label`, `text` (visible text), `style` (dict), `is_vertex`, `is_edge`,
`parent_id`, `source_id`, `target_id`, `x`, `y`, `width`, `height`, `bounds`,
`set_label(text)`, `set_style(mapping, **props)` (None removes a property),
`move(x, y, absolute=False)`, `resize(w, h)`.

## Layout (`drawio.layout`)

| Call | Effect |
|---|---|
| `layered(page, cells=None, direction="down", rank_gap=80, gap=40, x=40, y=40, ports=True)` | ranks along connectors; trees and flows; breaks cycles |
| `row(cells, x=None, y=None, gap=40, align="center")` | left to right |
| `column(cells, x=None, y=None, gap=40, align="center")` | top to bottom |
| `grid(cells, columns, x=None, y=None, gap=40)` | grid, each cell centred in its slot |

Pass shapes that share a parent. Call `page.fit()` afterwards.

## Checks (`drawio.lint`)

`check(document, fit=None, pages=None) -> list[Issue]`; `parse_fit("8.15x4.85in",
min_pt=12)`. `Issue` has `code, severity, page, cells, message, hint, data`.

## Rendering (`drawio.render`)

`render(source, output, *, page=None, fmt=None, scale=1, border=10, backend="auto",
aspect=None, transparent=False, background=None, download=True) -> Result(path, backend,
page, notes)`; `render_all(source, folder, fmt="png", **options)`.

`drawio.scene.build(page)` gives absolute shape boxes, label boxes and connector routes,
the same geometry that lint and the native renderer use.

## Text metrics (`drawio.text`)

`text_width(text, size, bold=False)`, `wrap(text, width, size)`, `measure(text, size,
width=None) -> (w, h, lines)`. Helvetica/Arial metrics; accented letters count as
their base letter; line height is 1.2 x font size.

## Environment variables

| Variable | Meaning |
|---|---|
| `DRAWIO_DESKTOP` | path of the draw.io desktop executable |
| `DRAWIO_CHROME` | Chrome/Chromium/Edge executable for the browser backend |
| `DRAWIO_VIEWER_JS` | local copy of viewer-static.min.js (offline browser backend) |
| `DRAWIO_FONT`, `DRAWIO_FONT_BOLD` | TrueType fonts for native raster output |
