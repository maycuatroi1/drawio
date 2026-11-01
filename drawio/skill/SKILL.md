---
name: drawio
description: Build, check and export editable draw.io (.drawio) diagrams in Python with drawio-python, then render them to PNG, SVG or PDF on any OS. Use for "vẽ sơ đồ drawio", "diagram bằng drawio", "sơ đồ kiến trúc", "flowchart", "architecture diagram", "ER diagram", "draw.io", ".drawio file", "export drawio to png/svg/pdf", "diagram for slides", "sửa file drawio", "sơ đồ bị chồng chữ / tràn chữ".
---

# drawio-python for agents

The library writes native draw.io XML: every box and arrow stays editable in draw.io.
Coordinates are explicit, so the loop is **build, lint, render, look, fix**. Do not guess
whether a diagram looks right; `drawio lint` and a rendered PNG tell you.

## 1. Set up once

```sh
python -c "import drawio" 2>/dev/null || pip install 'drawio-python[render]'
drawio doctor          # which render backends and fonts this machine has
```

- In a project venv: `pip install 'drawio-python[render]'` (or `uv pip install ...`).
- From a source checkout: `pip install -e '/path/to/drawio[render]'`.
- CLI only, no install: `uvx --from 'drawio-python[render]' drawio render x.drawio`.
- Never add `sys.path.insert(...)` for the library; install it instead.
- `drawio` on PATH may be this package or the draw.io desktop app. `python -m drawio ...`
  is always this package.

## 2. The loop

1. Write a generator script **in the project that owns the diagram** (not inside the
   library checkout), e.g. `diagrams/build_overview.py`, producing `overview.drawio`.
2. Run it, then check the layout:
   ```sh
   drawio lint overview.drawio            # exit 1 when there are warnings
   drawio lint overview.drawio --json     # findings with cell ids, numbers, fix hints
   ```
3. Render and **look at the PNG** before you report done:
   ```sh
   drawio render overview.drawio -o overview.png --scale 2
   ```
4. Fix what lint and the picture show, rerun. Deliver the `.drawio` (the editable
   source) plus renders if asked. Respect repo rules about committing images.

## 3. Build

```python
from drawio import Document, Theme
from drawio.shapes import color
from drawio.layout import layered

doc = Document(theme=Theme.drawio())  # draw.io's own look; Theme() is the library's
page = doc.add_page("Overview", id="overview")

api = page.box("API", 0, 0, 160, 60, id="api", style=color("blue"))
db = page.box("Orders DB", 0, 0, 160, 80, id="db", shape="cylinder", style=color("yellow"))
queue = page.box("Queue", 0, 0, 160, 60, id="queue", shape="rounded")
page.connect(api, db, "write", id="api-db")
page.connect(api, queue, "publish", id="api-queue", dashed=True)

layered(page, direction="right")  # or place shapes yourself
page.fit()  # grow containers and the page
doc.validate(check_bounds=True)
doc.save("overview.drawio", overwrite=True)
```

Key facts (full reference: `references/api.md`):

- `page.box(label, x, y, w, h, id=, parent=, style=, shape=, absolute=, autosize=)`.
  `shape=` takes `rounded, ellipse, circle, rhombus, cylinder, hexagon, triangle,
  parallelogram, document, cloud, process, note, card, step, actor` or any draw.io shape
  name. `page.ellipse`, `page.text`, `page.container`, `page.image(path_or_url, ...)`.
- Inside a container, x/y are **relative to the container** unless `absolute=True`.
  Waypoints are always page coordinates.
- `page.connect(src, dst, label, source_port=(1, .5), target_port=(0, .5),
  waypoints=[(x, y)], arrow=None|"block"|"open"|..., start_arrow=, dashed=)`.
  `arrow=None` gives an undirected line. Both ends must exist before you connect.
- IDs: give **every** cell a meaningful id, or none. Generated ids are `n1, n2...` for
  shapes and `e1...` for connectors, so naming your own cells `n1` collides.
- Layout without coordinate math: `drawio.layout.layered` (flows, trees),
  `row`, `column`, `grid`; then `page.fit()`. `page.autosize(cell)` grows a box to fit
  its label; `box(..., autosize=True)` does it on creation.
- Read geometry back: `cell.x/.y/.width/.height` (relative), `cell.bounds` (page),
  `page.find("Label")`, `page.children(container)`, `page.remove(cell)`.
- Colours: `drawio.shapes.color("blue" | "green" | "orange" | "yellow" | "red" |
  "purple" | "gray")`, the presets of draw.io's Style panel. `drawio shapes` lists all.

## 4. Check

`drawio lint` reports, per page: `text-overflow` (label bigger than its shape),
`overlap` / `text-overlap` / `container-overlap`, `outside-parent`, `edge-crosses-shape`,
`edge-crosses-label`, `label-overlap`, `edges-overlap`, `unsupported-shape` (info), and
with `--fit` also `small-text` and `aspect`. Text sizes are estimates from Helvetica
metrics, close to draw.io's wrapping; treat a finding as real and fix it.

- Text too big for its box: shorten the label, widen the box, or `page.autosize(cell)`.
  `drawio fit file.drawio --autosize` does it for a whole file.
- Connector through a shape: add `waypoints` around it, choose ports, or move shapes.
  `drawio inspect file.drawio --json` prints every shape box and connector route.
- A shape that encloses others is treated as a grouping backdrop, not an overlap.

## 5. Slides and documents

The size text ends up at is `fontSize x (box width / diagram width)`.

```sh
drawio lint deck.drawio --fit 8.15x4.85in --min-pt 12   # small-text and aspect findings
drawio render deck.drawio -o deck.png --scale 2 --aspect 8.15:4.85
```

Raise `Theme(font_size=...)` or make the diagram narrower until `small-text` is gone.
`--aspect` pads the canvas so picture boxes that crop (python-pptx, Keynote) do not cut it.
One picture per idea; avoid long sentences inside shapes.

## 6. Export

`drawio render IN -o OUT.{png,svg,pdf,jpg} [--page N|ID|NAME] [--all-pages] [--scale 2]`

| backend | needs | use |
|---|---|---|
| `auto` (default) | - | desktop if installed, else native |
| `native` | nothing for SVG; Pillow for PNG/JPEG/PDF | shapes this library makes and common draw.io shapes; SVG uses plain `<text>` (safe for LaTeX, rsvg-convert, Inkscape) |
| `browser` | `pip install 'drawio-python[browser-render]'` + Chrome/Edge or `playwright install chromium` | exact output of any diagram, icons and stencils included |
| `desktop` | draw.io desktop app | exact output, offline |

If `render` notes "drawn as rectangles", rerun with `--backend browser`. The browser
backend downloads the diagrams.net viewer once (set `DRAWIO_VIEWER_JS` offline).

## 7. Editing an existing .drawio someone else made

```python
doc = Document.load("their.drawio")
page = doc.get_page("page-id")  # or doc.pages[0]; `drawio info` lists pages
cell = page.find("Old label")[0]
cell.set_label("New label").set_style(fillColor="#dae8fc")
doc.save("their.drawio", overwrite=True)
```

- Back the file up or write to a new name first; keep the user's manual edits. Do not
  regenerate a file from a script once someone has edited it by hand.
- Other pages, cell IDs and metadata are preserved. Compressed pages are expanded.
- Combine files: `drawio merge out.drawio a.drawio b.drawio`; copy one page with
  `doc.import_page(other.pages[0])`; drop one with `doc.remove_page(page)`.
- Share for editing in the browser: `drawio url file.drawio` (the link embeds the
  diagram; anyone with it can read it). For Extras > Edit Diagram, paste
  `page.to_xml()`.

## 8. Errors

| message | fix |
|---|---|
| `ModuleNotFoundError: No module named 'drawio'` | install the package (section 1) |
| `Duplicate cell ID: n1 (...)` | your id clashes with a generated one; name all cells |
| `Unknown cell ID: x` | create both shapes before `connect`, or fix the id |
| `Child x extends outside its parent` | `page.fit(container)` or move the child |
| `Executable doesn't exist ... chromium` | nothing to do: Chrome/Edge is tried next; else `playwright install chromium` |
| `draw.io desktop needs a display on Linux` | install xvfb, or `--backend native` |
| `PNG, JPEG and PDF output needs Pillow` | `pip install 'drawio-python[render]'` |
