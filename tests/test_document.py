import base64
import copy
import math
import xml.etree.ElementTree as ET
import zlib
from urllib.parse import quote, unquote

import pytest

from drawio import Cell, Document, Page, Theme


def sample():
    doc = Document()
    page = doc.add_page("Overview", id="overview")
    box = page.container("Library", 500, 100, 400, 400, id="library")
    a = page.box("Articles", 20, 70, 180, 60, parent=box, id="articles")
    b = page.box("Drafts", 40, 150, id="drafts")
    page.connect(
        b,
        a,
        "approve",
        source_port=(1, 0.5),
        target_port=(0, 0.5),
        waypoints=[(400, 200), (400, 200)],
        dashed=True,
    )
    return doc, page, a, b


def compressed(model):
    compressor = zlib.compressobj(wbits=-15)
    data = quote(model, safe="~()*!.'-").encode()
    return base64.b64encode(compressor.compress(data) + compressor.flush()).decode()


def test_native_structure_and_nested_connectors():
    doc, page, a, b = sample()
    assert isinstance(page, Page) and isinstance(a, Cell)
    doc.validate(check_bounds=True)
    xml = ET.fromstring(doc.to_xml())
    cells = {c.get("id"): c for c in xml.findall(".//mxCell")}
    assert cells[a.id].get("parent") == "library"
    assert cells[a.id].find("mxGeometry").get("x") == "20"
    edge = next(c for c in cells.values() if c.get("edge") == "1")
    assert edge.get("source") == b.id and edge.get("target") == a.id
    assert "exitX=1;" in edge.get("style") and "entryY=0.5;" in edge.get("style")
    assert "dashed=1;" in edge.get("style")
    assert len(edge.findall("mxGeometry/Array/mxPoint")) == 2
    assert page.to_xml().startswith("<mxGraphModel")


def test_plain_text_unicode_and_html_are_distinct():
    doc = Document()
    page = doc.add_page('A & B "tabs"')
    label = 'A & B <script>alert("x")</script>\nTiếng Việt 📚'
    plain = page.box(label, 0, 0, style={"html": 1})
    rich = page.box("<b>Trusted &amp; formatted</b>", 250, 0, html=True)
    loaded = Document.from_xml(doc.to_xml()).pages[0]
    assert loaded.get(plain.id).element.get("value") == label
    assert "html=0;" in loaded.get(plain.id).element.get("style")
    assert loaded.get(rich.id).element.get("value") == "<b>Trusted &amp; formatted</b>"
    assert "html=1;" in loaded.get(rich.id).element.get("style")


def test_auto_ids_are_repeatable_and_skip_explicit_ids():
    def build():
        doc = Document()
        page = doc.add_page("Tab", id="page-2")
        page.box("A", 0, 0, id="n1")
        assert page.box("A", 300, 0).id == "n2"
        assert doc.add_page("Tab").id == "page-1"
        return doc.to_xml()

    assert build() == build()


def test_multiple_pages_and_same_cell_ids():
    doc = Document()
    for label in ("One", "Two", "Three"):
        page = doc.add_page(label)
        page.box(label, 0, 0, id="shared")
    loaded = Document.from_xml(doc.to_xml())
    assert [p.name for p in loaded.pages] == ["One", "Two", "Three"]
    assert loaded.get_page("page-2").get("shared").element.get("value") == "Two"
    with pytest.raises(ValueError, match="Unknown page"):
        loaded.get_page("missing")


def test_theme_and_overrides_do_not_mutate_style_mapping():
    doc = Document(theme=Theme(font_family="Arial", font_size=20))
    page = doc.add_page("One")
    options = {"fillColor": "#e7effb", "rounded": True}
    before = options.copy()
    box = page.box("A", 0, 0, style=options)
    page.text("Heading", 0, 200, style={"fontStyle": 1})
    assert options == before
    assert "fontFamily=Arial;" in box.element.get("style")
    assert "rounded=1;" in box.element.get("style")


@pytest.mark.parametrize("id", ["0", "1", "articles", "", "  ", "bad\x00id"])
def test_bad_or_duplicate_cell_ids(id):
    _, page, _, _ = sample()
    with pytest.raises(ValueError):
        page.box("A", 0, 0, id=id)


def test_duplicate_pages_and_foreign_references():
    doc, page, a, _ = sample()
    with pytest.raises(ValueError, match="Duplicate page"):
        doc.add_page("Two", id=page.id)
    other = doc.add_page("Two")
    same_id = other.box("Other Articles", 0, 0, id=a.id)
    with pytest.raises(ValueError, match="another page"):
        page.connect(a, same_id)
    with pytest.raises(ValueError, match="another page"):
        page.box("X", 0, 0, parent=same_id)
    with pytest.raises(ValueError, match="Unknown cell"):
        page.connect(a, "missing")
    with pytest.raises(ValueError, match="shape"):
        page.connect(a, "1")


@pytest.mark.parametrize(
    "geometry",
    [
        {"x": math.nan},
        {"y": math.inf},
        {"width": 0},
        {"height": -1},
        {"x": "10"},
        {"x": True},
    ],
)
def test_invalid_geometry(geometry):
    page = Document().add_page("Test")
    kwargs = {"x": 0, "y": 0, **geometry}
    with pytest.raises((ValueError, TypeError)):
        page.box("Bad", **kwargs)
    assert len(page.cells) == 2


@pytest.mark.parametrize("label", ["bad\x00", "bad\ud800", 123])
def test_invalid_labels_do_not_create_cells(label):
    page = Document().add_page("Test")
    with pytest.raises((ValueError, TypeError)):
        page.box(label, 0, 0)
    assert len(page.cells) == 2


@pytest.mark.parametrize(
    "kwargs",
    [
        {"source_port": (1.1, 0.5)},
        {"target_port": (-0.1, 0)},
        {"source_port": (0,)},
        {"source_port": (math.nan, 0)},
        {"waypoints": [(0,)]},
        {"waypoints": [(0, math.inf)]},
        {"style": {"fillColor": "red;html=1"}},
        {"style": {"bad=key": 1}},
    ],
)
def test_invalid_connector_options(kwargs):
    _, page, a, b = sample()
    count = len(page.cells)
    with pytest.raises((ValueError, TypeError)):
        page.connect(a, b, **kwargs)
    assert len(page.cells) == count


def test_validation_catches_manual_damage():
    doc, page, a, _ = sample()
    a.element.set("parent", "missing")
    with pytest.raises(ValueError, match="unknown parent"):
        doc.validate()
    a.element.set("parent", a.id)
    with pytest.raises(ValueError, match="cycle"):
        doc.validate()
    a.element.set("parent", "library")
    page.root.append(copy.deepcopy(a.element))
    with pytest.raises(ValueError, match="Duplicate cell"):
        doc.validate()


def test_child_bounds_are_opt_in():
    doc, page, a, _ = sample()
    a.element.find("mxGeometry").set("x", "399")
    doc.validate()
    with pytest.raises(ValueError, match="outside"):
        doc.validate(check_bounds=True)
    a.element.find("mxGeometry").set("relative", "1")
    doc.validate(check_bounds=True)


def test_load_edit_save_preserves_existing_pages_and_metadata(tmp_path):
    doc, _, _, _ = sample()
    doc.element.set("custom", "keep")
    source = ET.fromstring(doc.to_xml())
    original = source.find("diagram")
    original.set("custom-page", "keep too")
    original.find("mxGraphModel").set("custom-model", "preserved")
    xml = ET.tostring(source, encoding="unicode")
    loaded = Document.from_xml(xml)
    first = ET.tostring(loaded.pages[0].element)
    loaded.add_page("New tab").box("New", 0, 0)
    path = loaded.save(tmp_path / "document.drawio")
    assert ET.tostring(loaded.pages[0].element) == first
    again = Document.load(path)
    assert len(again.pages) == 2 and again.element.get("custom") == "keep"
    assert again.pages[0].element.get("custom-page") == "keep too"
    assert again.pages[0].model.get("custom-model") == "preserved"


def test_object_wrappers_and_free_edges_round_trip():
    doc, page, _, _ = sample()
    wrapper = ET.SubElement(
        page.root, "object", id="wrapped", label="Click", link="https://example.com/"
    )
    ET.SubElement(wrapper, "mxCell", vertex="1", parent="1")
    edge = ET.SubElement(page.root, "mxCell", id="free", edge="1", parent="1")
    geo = ET.SubElement(edge, "mxGeometry", relative="1", **{"as": "geometry"})
    ET.SubElement(geo, "mxPoint", x="1", y="2", **{"as": "sourcePoint"})
    ET.SubElement(geo, "mxPoint", x="3", y="4", **{"as": "targetPoint"})
    loaded = Document.from_xml(doc.to_xml())
    assert loaded.pages[0].get("wrapped").element.get("vertex") == "1"
    assert loaded.pages[0].root.find("object").get("link") == "https://example.com/"


def test_save_refuses_overwrite_and_cleans_temporary_files(tmp_path):
    doc, _, _, _ = sample()
    path = tmp_path / "test.drawio"
    path.write_text("original")
    with pytest.raises(FileExistsError):
        doc.save(path)
    assert path.read_text() == "original"
    assert list(tmp_path.iterdir()) == [path]
    doc.save(path, overwrite=True)
    assert Document.load(path).pages[0].name == "Overview"


def test_compressed_and_mixed_pages():
    doc, page, _, _ = sample()
    root = ET.fromstring(doc.to_xml())
    compressed_page = ET.SubElement(root, "diagram", id="second", name="Compressed")
    compressed_page.text = compressed(page.to_xml())
    loaded = Document.from_xml(ET.tostring(root, encoding="unicode"))
    assert len(loaded.pages) == 2
    assert loaded.pages[1].get("articles").element.get("value") == "Articles"
    assert Document.from_xml(page.to_xml()).pages[0].name == "Page 1"
    assert (
        Document.from_xml(ET.tostring(root.find("diagram"), encoding="unicode")).pages[0].name
        == "Overview"
    )


def test_editor_url_round_trip_without_network():
    doc, _, _, _ = sample()
    url = doc.to_url()
    assert url.startswith("https://app.diagrams.net/?splash=0#R")
    xml = unquote(zlib.decompress(base64.b64decode(url.split("#R")[1]), -15).decode())
    assert Document.from_xml(xml).to_xml() == doc.to_xml()


@pytest.mark.parametrize(
    "xml",
    [
        "<mxfile>",
        "<unexpected/>",
        "<mxfile/>",
        '<!DOCTYPE mxfile [<!ENTITY x "boom">]><mxfile/>',
        '<mxfile><diagram id="p" name="P"/></mxfile>',
        '<mxfile><diagram id="p" name="P">not-base64</diagram></mxfile>',
        '<mxfile><diagram id="p" name="P"><mxGraphModel/></diagram></mxfile>',
    ],
)
def test_bad_input(xml):
    with pytest.raises(ValueError):
        Document.from_xml(xml)


def test_limits_and_decompression_bomb(tmp_path):
    doc, _, _, _ = sample()
    xml = doc.to_xml()
    with pytest.raises(ValueError, match="limit"):
        Document.from_xml(xml, max_bytes=10)
    path = tmp_path / "large.drawio"
    path.write_text(xml)
    with pytest.raises(ValueError, match="limit"):
        Document.load(path, max_bytes=10)
    bomb = compressed("x" * 100000)
    with pytest.raises(ValueError, match="limit"):
        Document.from_xml(
            f'<mxfile><diagram id="p" name="P">{bomb}</diagram></mxfile>', max_bytes=5000
        )
    with pytest.raises(ValueError, match="max_bytes"):
        Document.from_xml(xml, max_bytes=0)


def test_page_rename_and_empty_document():
    doc = Document()
    with pytest.raises(ValueError, match="at least one"):
        doc.to_xml()
    p = doc.add_page("Before")
    p.name = "After"
    assert Document.from_xml(doc.to_xml()).pages[0].name == "After"
    with pytest.raises(ValueError):
        p.name = ""


def test_unknown_ancestor_and_missing_edge_endpoint_are_validation_errors():
    doc, page, a, b = sample()
    a.element.set("parent", b.id)
    b.element.set("parent", "missing")
    with pytest.raises(ValueError, match="unknown ancestor"):
        doc.validate()
    b.element.set("parent", "1")
    edge = next(c.element for c in page.cells if c.element.get("edge") == "1")
    edge.attrib.pop("target")
    with pytest.raises(ValueError, match="target endpoint"):
        doc.validate()


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_bad_limit_rejected_before_reading_file(limit):
    with pytest.raises(ValueError, match="max_bytes"):
        Document.load("nonexistent", max_bytes=limit)


def test_invalid_background_does_not_append_page():
    doc = Document()
    with pytest.raises(ValueError):
        doc.add_page("Bad", background="bad\x00")
    assert not doc.pages and len(doc.element) == 0
