# drawio-python

Build editable draw.io diagrams in Python. Save XML files without Selenium,
Chrome, an export server, or runtime dependencies. Requires Python 3.9 or newer.

The native API supports multiple pages, nested containers, styled shapes,
connector ports and waypoints. The existing `Graph` / `Node` API still works.

## Install this checkout

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
```

These instructions use the updated source. The version on PyPI may differ.

## Create a diagram

```python
from drawio import Document

document = Document()
page = document.add_page("Publishing", id="publishing")

source = page.box("Draft", 40, 180, id="draft")
library = page.container("Library", 500, 80, 350, 350, id="library")
articles = page.box("Articles", 20, 70, 310, 70, parent=library)
page.box("Images", 20, 180, 310, 70, parent=library)

page.connect(
    source, articles, "publish",
    source_port=(1, 0.5), target_port=(0, 0.5),
    waypoints=[(370, 225), (370, 185)],
)

document.add_page("Notes").text("A second editable tab", 40, 40)
document.validate(check_bounds=True)
document.save("publishing.drawio")
```

Open the file in draw.io or diagrams.net. Each block and connector remains a
native editable object. Child coordinates are relative to the parent container;
connector waypoints use page coordinates.

`save()` refuses to replace an existing file. Pass `overwrite=True` when you
intend to update it. File writing uses an atomic replace or exclusive creation.

## Add a page to an existing file

```python
from drawio import Document

document = Document.load("publishing.drawio")
page = document.add_page("Review Details", id="review-details")
page.box("Editorial review", 40, 80)
document.save("publishing-v2.drawio")
```

The loader accepts uncompressed and compressed draw.io XML. It retains existing
page IDs, cells, geometry and metadata; it expands compressed pages on output.
It does not preserve byte-for-byte formatting, signatures or compression.

## Style and labels

```python
from drawio import Document, Theme

document = Document(theme=Theme(font_family="Arial", font_size=20))
page = document.add_page("Styled")
page.box("Plain text: A & B < C", 40, 40,
         style={"fillColor": "#e7effb", "fontStyle": 1})
page.box("<b>Trusted HTML</b><br/>Subtitle", 300, 40, html=True)
```

Labels default to plain text. Use `html=True` only for markup you trust. Style
mappings use draw.io property names such as `fillColor`, `shape` and `fontSize`.
XML escaping is handled by the writer.

## CLI

```sh
python -m drawio new empty.drawio --name Overview
python -m drawio validate publishing.drawio --check-bounds
python -m drawio info publishing.drawio
python -m drawio url publishing.drawio
```

The installed `drawio` command exposes the same interface. `url` prints an editor
link containing the complete diagram. Generating the URL makes no network
request; anyone with the link can read its embedded content.

For an open editor's **Extras > Edit Diagram** dialog, use `page.to_xml()` to
obtain that page's `mxGraphModel`. Importing through that dialog may retain the
editor's current Grid, Page View and Background settings.

## Existing Graph / Node API

```python
from drawio import Graph, Node

graph = Graph(name="Review")
a = Node("Draft", shape="rectangle", x=40, y=80)
b = Node("Published", shape="rectangle", x=400, y=80)
graph.add_nodes([a, b])
a >> "approve" >> b

graph.render("review.drawio", show=False)
```

`.drawio` and `.xml` rendering now uses the native writer and returns the output
path. `Graph.render()` retains its overwrite behavior. `show=True` saves first,
then asks the default browser to open an encoded editor URL; it no longer waits
for console input. Tests and examples use `show=False`.

Unpositioned legacy nodes use a simple grid, including disconnected graphs and
cycles. Use `Node(x=..., y=...)` or the native `Page` API for an authored layout.
The library does not provide automatic graph layout or SVG/PNG rendering.

`to_draw_io_csv()` and `to_draw_io()` still return the legacy CSV and text forms.
The basic Mermaid importer retains the historical import path:

```python
from drawio.itergrations.mermaid.mermaid_controller import MermaidController

graph = MermaidController().load("flowchart LR; A[Draft] -->|approve| B[Published]")
graph.render("mermaid.drawio")
```

Supported Mermaid input includes node declarations, `-->`, `-->|label|`, chained
edges, and rectangular, circular, parenthesized and diamond node labels. Direction
headers are accepted, but the legacy renderer uses the grid described above.
Subgraphs, styling directives and other edge syntax raise errors rather than
silently dropping content. This importer is not a complete Mermaid parser.

## Examples and optional integrations

```sh
python examples/native_document.py
python examples/complex-example.py
```

The first example writes `output/publishing.drawio` with two tabs and nested
containers. The second demonstrates loading a file and adding a page.

Optional extras:

- `.[pdf]`: Python Graphviz binding; also install the Graphviz `dot` executable.
- `.[browser]`: legacy Selenium helpers for callers importing `DrawIOBrowser`
  directly. They are not part of native rendering and are not live-browser
  tested by the default suite.
- `.[excel]`: dependencies for the existing ERD spreadsheet exporter.
- `.[docs]`: MkDocs.

## Development

```sh
make lint
make test
make build
```

Tests write real XML and run examples in temporary directories. They do not
install packages, download browser drivers, or launch Chrome. See
[the API reference](docs/index.md) and [contribution guide](CONTRIBUTING.md).
