import os
import stat
import sys

import pytest

from drawio import Document, Theme
from drawio.shapes import SHAPES, color


def test_save_respects_umask_and_keeps_mode_on_overwrite(tmp_path):
    doc = Document()
    doc.add_page("A").box("x", 0, 0)
    path = doc.save(tmp_path / "a.drawio")
    assert list(tmp_path.iterdir()) == [path]  # no temporary file left behind
    if sys.platform.startswith("win"):
        return
    umask = os.umask(0)
    os.umask(umask)
    assert stat.S_IMODE(path.stat().st_mode) == 0o666 & ~umask
    os.chmod(path, 0o640)
    doc.save(path, overwrite=True)
    assert stat.S_IMODE(path.stat().st_mode) == 0o640


def test_duplicate_generated_id_explains_the_clash():
    page = Document().add_page("A")
    page.box("auto", 0, 0)
    with pytest.raises(ValueError, match="generated for cells created without an id"):
        page.box("mine", 0, 0, id="n1")
    with pytest.raises(ValueError) as plain:
        page.box("x", 0, 0, id="db")
        page.box("y", 0, 0, id="db")
    assert "generated" not in str(plain.value)


def test_shapes_images_and_arrows(tmp_path):
    page = Document().add_page("A")
    db = page.box("DB", 0, 0, shape="cylinder")
    assert db.style["shape"] == "cylinder3"
    assert page.ellipse("E", 0, 0).style["shape"] == "ellipse"
    assert page.box("S", 0, 0, shape="mxgraph.aws4.lambda").style["shape"] == "mxgraph.aws4.lambda"
    assert set(SHAPES) >= {"rounded", "rhombus", "actor", "hexagon"}
    png = tmp_path / "dot.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    picture = page.image(png, 0, 0, label="Dot")
    assert picture.style["image"].startswith("data:image/png,iVBOR")
    assert page.image("data:image/svg+xml;base64,PHN2Zy8+", 0, 0).style["image"] == (
        "data:image/svg+xml,PHN2Zy8+"
    )
    with pytest.raises(ValueError):
        page.image(tmp_path / "notes.txt", 0, 0)
    line = page.connect(db, picture, arrow=None)
    assert line.style["endArrow"] == "none" and line.style["startArrow"] == "none"
    both = page.connect(db, picture, arrow="open", start_arrow="oval")
    assert both.style["endArrow"] == "open" and both.style["startArrow"] == "oval"
    assert page.connect(db, picture).style["endArrow"] == "block"


def test_theme_drawio_defaults():
    page = Document(theme=Theme.drawio()).add_page("A")
    box = page.box("x", 0, 0)
    edge = page.connect(box, page.box("y", 300, 0))
    assert box.style["fontSize"] == "12" and box.style["strokeColor"] == "#000000"
    assert box.style["strokeWidth"] == "1" and box.style["spacing"] == "2"
    assert edge.style["endArrow"] == "classic" and edge.style["strokeWidth"] == "1"
    assert color("blue") == {"fillColor": "#dae8fc", "strokeColor": "#6c8ebf"}
    with pytest.raises(ValueError, match="Unknown colour"):
        color("teal")


def test_absolute_coordinates_bounds_and_moves():
    page = Document().add_page("A")
    outer = page.container("Outer", 100, 100, 400, 300)
    inner = page.container("Inner", 50, 60, 200, 150, parent=outer)
    child = page.box("C", 180, 200, 40, 30, parent=inner, absolute=True)
    assert (child.x, child.y) == (30, 40)
    assert child.bounds == (180, 200, 40, 30)
    child.move(160, 170, absolute=True)
    assert (child.x, child.y) == (10, 10)
    child.resize(50, 20)
    assert (child.width, child.height) == (50, 20)
    assert page.children(inner) == (page.get(child.id),) or page.children(inner)[0].id == child.id


def test_cell_properties_and_set_style():
    page = Document().add_page("A")
    rich = page.box("<b>Bold</b><br>line", 0, 0, html=True)
    assert rich.text == "Bold\nline" and rich.is_vertex and not rich.is_edge
    rich.set_style({"fillColor": "#ff0000"}, rounded=None)
    assert rich.style["fillColor"] == "#ff0000" and "rounded" not in rich.style
    rich.set_label("Plain")
    assert page.find("Plain")[0].id == rich.id


def test_autosize_and_fit():
    page = Document().add_page("A")
    group = page.container("Group", 0, 0, 100, 60)
    long = "A label long enough that it has to wrap over several lines"
    box = page.box(long, 10, 40, 120, 30, parent=group, autosize=True)
    assert box.height > 30 and box.width == 120
    word = page.box("Supercalifragilistic", 0, 300, 60, 40)
    page.autosize(word, max_width=400)
    assert word.width > 60
    page.fit(padding=10)
    assert group.width >= box.x + box.width + 10
    assert group.height >= box.y + box.height + 10
    assert float(page.model.get("pageHeight")) >= 340


def test_remove_cascades_to_children_and_connectors():
    page = Document().add_page("A")
    group = page.container("G", 0, 0, 300, 200, id="g")
    a = page.box("a", 10, 40, 50, 30, parent=group, id="a")
    b = page.box("b", 400, 0, 50, 30, id="b")
    page.connect(a, b, id="ab")
    page.connect(b, b, id="loop")
    page.remove(group)
    assert {c.id for c in page.cells} == {"0", "1", "b", "loop"}
    with pytest.raises(ValueError):
        page.remove("1")
    page.validate()


def test_import_and_remove_pages():
    first = Document()
    first.add_page("One", id="p").box("x", 0, 0)
    second = Document()
    second.add_page("Two", id="p")
    copied = second.import_page(first.pages[0])
    assert copied.id == "page-1" and copied.name == "One" and len(copied.shapes) == 1
    renamed = second.import_page(first.pages[0], id="three", name="Three")
    assert renamed.id == "three"
    with pytest.raises(ValueError, match="Duplicate page ID"):
        second.import_page(first.pages[0], id="three")
    second.remove_page("three")
    assert [p.id for p in second.pages] == ["p", "page-1"]
    with pytest.raises(ValueError):
        second.remove_page(first.pages[0])
    reloaded = Document.from_xml(second.to_xml())
    assert [p.id for p in reloaded.pages] == ["p", "page-1"]
