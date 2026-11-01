# drawio-python

Build, check and export editable draw.io diagrams in Python. The library writes
native draw.io XML (every shape stays editable in draw.io), measures labels, finds
layout problems, lays shapes out, and renders PNG, SVG or PDF on Linux, macOS and
Windows. The core needs only the Python standard library; Python 3.9 or newer.

It is built to be driven by coding agents as much as by people: every command has
`--json` output, and an agent skill ships with the package.

## Install

```sh
pip install 'drawio-python[render]'      # core + PNG/JPEG/PDF output (Pillow)
pip install drawio-python                # core only: build, lint, SVG
pip install 'drawio-python[browser-render]'  # exact rendering of any draw.io file
```

From a checkout: `python -m pip install -e '.[render,test]'`. Check what the machine
can render with `drawio doctor`.

## Agents

```sh
drawio skill install          # into ~/.claude/skills, ~/.codex/skills and/or ~/.agents/skills
drawio skill show             # print the skill
```

The skill (`drawio/skill/SKILL.md`) teaches the loop **build, `drawio lint`,
`drawio render`, look, fix**, the API, slide sizing and the common errors.

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

## Shapes, layout and fitting text

```python
from drawio import Document, Theme
from drawio.layout import layered
from drawio.shapes import color

doc = Document(theme=Theme.drawio())   # the draw.io editor's own look
page = doc.add_page("Flow")
start = page.box("Start", 0, 0, 120, 50, shape="rounded", style=color("green"))
check = page.box("Valid?", 0, 0, 120, 80, shape="rhombus")
store = page.box("Orders", 0, 0, 120, 80, shape="cylinder", style=color("yellow"))
page.connect(start, check)
page.connect(check, store, "yes")
layered(page, direction="down")        # ranks along the connectors; also row/column/grid
page.fit()                             # grow containers and the page around the shapes
doc.save("flow.drawio", overwrite=True)
```

- `shape=` accepts `rounded, ellipse, circle, rhombus, cylinder, hexagon, triangle,
  parallelogram, document, cloud, process, note, card, step, actor` or any draw.io
  shape name; `page.image()` embeds a picture file.
- `connect(..., arrow=None)` draws an undirected line; `arrow` and `start_arrow` take
  any draw.io marker (`drawio shapes` lists them).
- `box(..., absolute=True)` takes page coordinates inside a container;
  `box(..., autosize=True)` or `page.autosize(cell)` grows a box to fit its label.
- Cells expose `x`, `y`, `width`, `height`, `bounds`, `style`, `text`, `move()`,
  `resize()`, `set_style()`; pages offer `find()`, `children()`, `remove()`;
  documents offer `import_page()` and `remove_page()`.

## Check the layout

```sh
drawio lint flow.drawio                     # exit status 1 when something is wrong
drawio lint deck.drawio --fit 8.15x4.85in   # also: text below 12 pt once placed on a slide
drawio lint flow.drawio --ignore aspect -v  # pick codes with --select/--ignore; -v prints info
drawio inspect flow.drawio --json           # every shape box and connector route
```

Lint reports overflowing labels, overlapping shapes and labels, connectors that run
through shapes or labels or hide under a shape painted after them, children outside
containers, style properties draw.io ignores, and (with `--fit`) text that ends up too
small and aspect-ratio mismatches. Connector routes come from a port of draw.io's own
router (`drawio/routing.py`, checked against the diagrams.net viewer); text widths are
estimated from Helvetica/Arial metrics, close to draw.io's wrapping.

## Render

```sh
drawio render flow.drawio -o flow.png --scale 2
drawio render flow.drawio -o flow.svg              # plain SVG text, no foreignObject
drawio render deck.drawio -o slide.png --aspect 16:9
drawio render big.drawio --all-pages -f pdf
```

| Backend | Requirements | Output |
|---|---|---|
| `native` | none for SVG; Pillow for PNG, JPEG, PDF | shapes this library makes and common draw.io shapes |
| `desktop` | [draw.io desktop](https://github.com/jgraph/drawio-desktop/releases) | exact |
| `browser` | `[browser-render]` extra plus Chrome, Edge or `playwright install chromium` | exact, including stencils and icons |
| `auto` | | desktop when installed, otherwise native |

The browser backend loads the official diagrams.net viewer, downloaded once to the
user cache (set `DRAWIO_VIEWER_JS` to work offline). On Linux the desktop backend
needs a display or `xvfb-run`. Native PDF is vector when `cairosvg` or `rsvg-convert`
is available, otherwise a raster image. `drawio doctor` reports all of this.

## CLI

```sh
drawio new empty.drawio --name Overview
drawio validate publishing.drawio --check-bounds
drawio info publishing.drawio
drawio url publishing.drawio
drawio render | lint | inspect | fit | layout | merge | shapes | doctor | skill
```

`python -m drawio` runs the same commands, which helps when the draw.io desktop
app also installed a `drawio` command. Commands that report take `--json`. `url` prints an editor
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
cycles. Use `Node(x=..., y=...)` or the native `Page` API with `drawio.layout` for
an authored or automatic layout.

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

- `.[render]`: Pillow, for PNG, JPEG and PDF output of the native renderer.
- `.[browser-render]`: Playwright, for the exact `browser` render backend.
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

Tests write real XML, render with the native backend and run examples in
temporary directories. They do not install packages, download browser drivers, or
launch Chrome. See
[the API reference](docs/index.md) and [contribution guide](CONTRIBUTING.md).

## License

drawio-python is released into the public domain (see `LICENSE`), except
`drawio/routing.py`, a port of connector routing from mxGraph by JGraph Ltd, which is
under the Apache License 2.0 (`LICENSES/Apache-2.0.txt`).
