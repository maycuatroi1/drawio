# Native XML API

Install the checkout with `python -m pip install -e '.[test]'`.
See the repository README for the quick start and legacy API migration notes.

## Document

```python
from drawio import Document, Theme

doc = Document(theme=Theme(font_family="Helvetica", font_size=18))
page = doc.add_page("Overview", id="overview", width=1600, height=1000)
```

| Method | Result |
| --- | --- |
| `add_page(name, id=None, width=1600, height=1000, background="#ffffff")` | New editable `Page` |
| `get_page(id)` | Page with that ID, or `ValueError` |
| `pages` | Tuple of pages in document order |
| `validate(check_bounds=False)` | Check page/cell IDs, endpoints and parent hierarchy |
| `to_xml(pretty=True)` | Complete `mxfile` XML string |
| `save(path, overwrite=False)` | Save UTF-8 XML and return a `Path` |
| `to_url()` | Encoded diagrams.net editor URL; no network access |
| `Document.load(path, max_bytes=...)` | Load UTF-8 `.drawio` / `.xml` |
| `Document.from_xml(xml, max_bytes=...)` | Load an XML string or UTF-8 bytes |

Explicit IDs are useful for stable diffs. Generated IDs follow insertion order
and skip IDs already in use. Page IDs must be unique within a document; cell IDs
must be unique within a page. Different pages may reuse a cell ID.

Loading accepts `mxfile`, a single `diagram`, or a standalone `mxGraphModel`.
The default input and expanded-model limit is 10 MiB. You can raise `max_bytes`
for trusted larger documents. The loader rejects DTD/entity declarations and
invalid compressed data. It preserves supported XML structure and unknown
metadata, including draw.io `object` wrappers; it is not a full schema validator
for every draw.io plugin or custom shape.

## Page and Cell

```python
box = page.box("Input", 40, 80, width=200, height=90, id="input")
group = page.container("Output", 500, 80, 360, 360, id="output")
child = page.box("Article", 20, 70, 320, 80, parent=group)
page.text("Overview", 40, 20, 700, 40, style={"fontSize": 28})
page.connect(box, child, "publish")
```

`box`, `container` and `text` accept `id`, `parent`, `style` and `html` keyword
arguments and return a `Cell`. Use a returned `Cell` or an existing cell ID as a
parent or connector endpoint. References cannot cross page boundaries.

- `box(label, x, y, width=200, height=90, ...)`: native shape.
- `container(label, x, y, width, height, ...)`: shape with a top-aligned title and
  nested child blocks.
- `text(label, x, y, width=400, height=40, ...)`: borderless text.
- `connect(source, target, label="", ...)`: native orthogonal connector.
- `get(id)`: existing cell reference.
- `cells`: tuple of cell references, including root/layer cells.
- `name`: editable tab name.
- `to_xml()`: the current page's `mxGraphModel` XML.

A child's `(x, y)` is relative to its parent. Reserve space for the container
heading yourself. Nested container coordinates follow the same rule. The writer
does not pack, resize or align child blocks for you.

`validate(check_bounds=True)` also checks ordinary child rectangles against
parent bounds. Relative ports are exempt from this bounds check. Validation does
not measure text, detect shape overlaps or guarantee optimal connector routing.

`Cell.element`, `Page.model`, `Page.element` and `Document.element` expose the
underlying ElementTree elements for advanced XML editing. Call `validate()`
after a manual change; prefer the builder methods for creating cells and pages.

## Connectors

```python
page.connect(
    box, child, "publish",
    id="publish-edge",
    source_port=(1, 0.5),
    target_port=(0, 0.5),
    waypoints=[(400, 125), (400, 190)],
    dashed=True,
    style={"strokeColor": "#246a52", "fontSize": 16},
)
```

Ports are normalized `(x, y)` pairs in `[0, 1]`. `(1, 0.5)` is the right edge's
midpoint; `(0.5, 1)` is the bottom midpoint. Omit ports to let draw.io choose them.
Waypoints use page coordinates even when an endpoint belongs to a container.
Labels on connectors use plain text.

## Styles and text

`Theme` sets `font_family`, `font_size`, `fill_color`, `stroke_color`,
`text_color` and `line_color`. Per-cell style dictionaries override the defaults.
Style keys use draw.io names; booleans become `1` or `0`. Semicolons in style
values and delimiters in keys are rejected.

Plain-text labels support Unicode, quotes, newlines and XML-significant
characters. The writer escapes XML. A style dictionary cannot opt into HTML:
pass `html=True` to a shape method when you intend to render trusted markup.

```python
page.box("<b>Title</b><br/>Subtitle", 40, 300, html=True)
```

XML generation works offline. To inspect the visual result, open the file in
draw.io. Use that editor or draw.io Desktop for image/PDF exports.
