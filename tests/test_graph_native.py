import csv
import io
import subprocess
import sys

import pytest

from drawio import Document, Graph, Node
from drawio.entities.drawio_config.drawio_config import DrawIOConfig


def test_native_legacy_render_and_paths(tmp_path, monkeypatch):
    monkeypatch.setattr("webbrowser.open", lambda *a, **k: pytest.fail("Unexpected browser launch"))
    a, b = Node("Same", id="a"), Node("Same", id="b")
    c = Node("C", id="c")
    g = Graph(name="Legacy")
    g.add_nodes([a, b])
    a >> "keeps label" >> b
    b >> c
    c >> a
    a >> b
    a >> b
    assert len(g.nodes) == 3 and len(g.edges) == 4
    assert len(b.parents) == 2 and len(a.children) == 2
    file = tmp_path / "dots.in.name.drawio"
    assert g.render(file) == str(file)
    doc = Document.load(file)
    assert sum(c.element.get("edge") == "1" for c in doc.pages[0].cells) == 4
    assert "keeps label" in g.to_draw_io_xml()
    assert g.render(tmp_path / "upper.XML").endswith("upper.XML")


def test_connections_register_unlisted_nodes():
    g = Graph()
    a, b = Node("A"), Node("B")
    g.add_node(a)
    a >> "label" >> b
    assert b in g.nodes and b.graph is g
    assert b.parents[0] is a.children[0] is g.edges[0]


def test_same_labels_do_not_collapse_distinct_edges():
    a, b, c = Node("Same"), Node("Same"), Node("Same")
    g = Graph()
    g.add_nodes([a, b, c])
    a >> b
    a >> c
    assert len(g.edges) == 2


def test_incomplete_and_foreign_graphs():
    a, b = Node("A"), Node("B")
    g = Graph(a)
    a >> "pending"
    with pytest.raises(ValueError, match="Unfinished"):
        g.to_draw_io_xml()
    Graph(b)
    with pytest.raises(ValueError, match="different graphs"):
        a >> b
    with pytest.raises(ValueError, match="Duplicate node"):
        g.add_node(Node("Different", id=a.id))


def test_explicit_geometry_and_simple_grid():
    g = Graph()
    a, b = Node("A", x=12, y=34, width=250), Node("B")
    g.add_nodes([a, b])
    page = g.to_document().pages[0]
    assert page.get(a.id).element.find("mxGeometry").get("x") == "12"
    assert float(page.get(b.id).element.find("mxGeometry").get("x")) > 250


def test_csv_repeatable_and_escaped():
    g = Graph()
    g.add_node(Node('Comma, "quote"\nnewline', id="a"))
    cfg = DrawIOConfig()
    first = g.to_draw_io_csv(cfg)
    assert first == g.to_draw_io_csv(cfg)
    assert len(cfg.column_names) == 8
    lines = first.splitlines(keepends=True)
    data = "".join(line for line in lines if not line.startswith("#"))
    rows = list(csv.reader(io.StringIO(data)))
    assert len(rows[0]) == len(rows[1]) == 8
    assert rows[1][1] == g.nodes[0].name


def test_core_imports_without_browser_dependencies():
    code = """
import sys
class Block:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'selenium', 'webdriver_manager', 'shortuuid', 'graphviz'}:
            raise RuntimeError('Optional import: '+fullname)
sys.meta_path.insert(0, Block())
from drawio import Document, Graph, Node
g = Graph(Node('A'))
assert '<mxfile' in g.to_draw_io_xml()
"""
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr


def test_show_is_explicit(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("webbrowser.open", calls.append)
    g = Graph(Node("A"))
    g.render(tmp_path / "shown.drawio", show=True)
    assert len(calls) == 1 and "#R" in calls[0]


def test_missing_pdf_extra_is_actionable(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "graphviz", None)
    with pytest.raises(RuntimeError, match=r"drawio-python\[pdf\]"):
        Graph(Node("A")).render(tmp_path / "diagram.pdf")


def test_repeated_labelled_edges_and_reserved_ids():
    g = Graph()
    a, b, c = Node("A", id="0"), Node("B", id="1"), Node("C", id="node-0")
    g.add_nodes([a, b, c])
    a >> "same" >> b
    a >> "same" >> b
    assert len(g.edges) == len(a.children) == len(b.parents) == 1
    document = g.to_document()
    document.validate()
    assert len([c for c in document.pages[0].cells if c.element.get("vertex") == "1"]) == 3
