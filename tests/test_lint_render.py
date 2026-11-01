import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from drawio import Document
from drawio.lint import check, parse_fit
from drawio.render import desktop, parse_aspect, render, render_all
from drawio.scene import build, route


def codes(document, **kwargs):
    return sorted({issue.code for issue in check(document, **kwargs)})


def test_routes_follow_draw_io_cases():
    style = {"edgeStyle": "orthogonalEdgeStyle"}
    side = route((0, 0, 100, 50), (300, 0, 100, 50), style, [])
    assert side == [(100, 25), (300, 25)]
    stacked = route((0, 0, 100, 50), (0, 200, 100, 50), style, [])
    assert stacked == [(50, 50), (50, 200)]
    diagonal = route((0, 0, 100, 50), (300, 200, 100, 50), style, [])
    assert diagonal[0] == (100, 25) and diagonal[-1] == (300, 225)
    assert all(a[0] == b[0] or a[1] == b[1] for a, b in zip(diagonal, diagonal[1:]))
    ported = {**style, "exitX": "0.5", "exitY": "1", "entryX": "0.5", "entryY": "0"}
    assert route((0, 0, 100, 50), (200, 200, 100, 50), ported, [])[0] == (50, 50)
    via = route((0, 0, 100, 50), (300, 0, 100, 50), style, [(200, 150)])
    assert any(
        min(a[0], b[0]) <= 200 <= max(a[0], b[0]) and a[1] == b[1] == 150
        for a, b in zip(via, via[1:])
    )
    straight = route((0, 0, 100, 100), (300, 0, 100, 100), {}, [])
    assert straight == [(100, 50), (300, 50)]


def test_clean_diagram_has_no_findings():
    doc = Document()
    page = doc.add_page("Clean")
    a = page.box("Client", 40, 40, 160, 60)
    b = page.box("Server", 400, 40, 160, 60)
    page.connect(a, b, "HTTPS")
    assert check(doc) == []


def test_lint_finds_the_problems_agents_hit():
    doc = Document()
    page = doc.add_page("Broken")
    page.box("A plain label that is much too long for this box to hold", 20, 20, 160, 60)
    a = page.box("A", 20, 200, 100, 50)
    b = page.box("B", 400, 200, 100, 50)
    page.box("In the way", 200, 190, 100, 70)
    page.connect(a, b, "long connector label")
    page.box("Overlapping", 60, 40, 200, 40)
    group = page.container("Group", 600, 0, 100, 100)
    page.box("child", 50, 60, 100, 100, parent=group)
    found = codes(doc)
    for code in ("text-overflow", "overlap", "edge-crosses-shape", "label-overlap"):
        assert code in found
    assert "outside-parent" in found
    issue = next(i for i in check(doc) if i.code == "text-overflow")
    assert issue.hint and issue.data["shape"] and issue.to_dict()["severity"] == "warning"


def test_backdrop_shapes_are_not_overlaps():
    doc = Document()
    page = doc.add_page("Zones")
    page.box("", 0, 0, 600, 300, style={"fillColor": "#dae8fc"})  # a plain zone rectangle
    a = page.box("A", 40, 100, 100, 50)
    b = page.box("B", 400, 100, 100, 50)
    outside = page.box("C", 700, 100, 100, 50)
    page.connect(a, b)
    page.connect(b, outside)
    assert check(doc) == []


def test_fit_reports_small_text_and_aspect():
    doc = Document()
    page = doc.add_page("Wide")
    page.box("tiny", 0, 0, 2000, 100, style={"fontSize": 12})
    found = codes(doc, fit=parse_fit("8.15x4.85in"))
    assert "small-text" in found and "aspect" in found
    assert parse_fit("16cm").unit == "cm"
    with pytest.raises(ValueError):
        parse_fit("big")


def sample(tmp_path):
    doc = Document()
    page = doc.add_page("Render", id="render")
    a = page.box("Tiếng Việt & <xml>", 0, 0, 160, 60, shape="rounded")
    b = page.box("DB", 300, 0, 120, 80, shape="cylinder")
    page.ellipse("E", 0, 150)
    page.box("odd", 300, 150, shape="mxgraph.aws4.lambda")
    page.connect(a, b, "write", dashed=True)
    doc.add_page("Second", id="second").box("two", 0, 0)
    path = tmp_path / "sample.drawio"
    doc.save(path)
    return path


def test_native_svg_has_plain_text_and_escapes(tmp_path):
    path = sample(tmp_path)
    result = render(path, tmp_path / "out.svg", backend="native")
    assert result.backend == "native" and result.page == "render"
    assert any("mxgraph.aws4.lambda" in note for note in result.notes)
    svg = (tmp_path / "out.svg").read_text(encoding="utf-8")
    root = ET.fromstring(svg)
    assert "foreignObject" not in svg
    texts = "".join(root.itertext())
    assert "Tiếng Việt &" in texts and "<xml>" in texts and "write" in texts
    assert root.get("viewBox")


def test_native_png_pdf_jpg_and_aspect(tmp_path):
    pytest.importorskip("PIL")
    from PIL import Image

    path = sample(tmp_path)
    one = render(path, tmp_path / "one.png", backend="native")
    two = render(path, tmp_path / "two.png", backend="native", scale=2)
    w1, h1 = Image.open(one.path).size
    w2, h2 = Image.open(two.path).size
    assert abs(w2 - 2 * w1) <= 2 and abs(h2 - 2 * h1) <= 2
    padded = render(path, tmp_path / "wide.png", backend="native", aspect="16:9")
    w, h = Image.open(padded.path).size
    assert w / h == pytest.approx(16 / 9, rel=0.02)
    assert render(path, tmp_path / "x.pdf", backend="native").path.read_bytes()[:4] == b"%PDF"
    assert Image.open(render(path, tmp_path / "x.jpg", backend="native").path).format == "JPEG"
    second = render(path, tmp_path / "second.png", page="Second", backend="native")
    assert second.page == "second"
    results = render_all(path, tmp_path / "all", fmt="svg", backend="native")
    assert [r.path.name for r in results] == ["render.svg", "second.svg"]


def test_render_argument_errors(tmp_path):
    path = sample(tmp_path)
    with pytest.raises(ValueError, match="format"):
        render(path, tmp_path / "x.gif")
    with pytest.raises(ValueError, match="backend"):
        render(path, tmp_path / "x.png", backend="magic")
    with pytest.raises(ValueError, match="out of range"):
        render(path, tmp_path / "x.svg", page=7)
    with pytest.raises(ValueError, match="No page"):
        render(path, tmp_path / "x.svg", page="missing")
    assert parse_aspect("16:9") == pytest.approx(16 / 9) and parse_aspect(None) is None


def test_desktop_detection_and_command(tmp_path, monkeypatch):
    monkeypatch.setenv("DRAWIO_DESKTOP", str(tmp_path / "missing"))
    assert desktop.find() is None
    script = tmp_path / "drawio"
    script.write_text("#!/usr/bin/env python3\nprint('hi')\n")
    assert desktop._is_ours(str(script))
    launcher = tmp_path / "drawio.exe"  # pip's Windows launcher: binary stub + appended script
    launcher.write_bytes(
        b"MZ\x90\x00" + b"\x00" * 4096 + b"PK\x03\x04import re\nfrom drawio.__main__ import main\n"
    )
    assert desktop._is_ours(str(launcher))
    import sysconfig

    assert desktop._is_ours(str(Path(sysconfig.get_path("scripts")) / "drawio"))
    exe = tmp_path / "draw.io"
    exe.write_bytes(b"\x7fELF")
    monkeypatch.setenv("DRAWIO_DESKTOP", str(exe))
    assert desktop.find() == str(exe)

    calls = []

    class Done:
        returncode = 0
        stdout = stderr = ""

    def fake_run(command, **kwargs):
        calls.append(command)
        (tmp_path / "out.png").write_bytes(b"png")
        return Done()

    monkeypatch.setattr(desktop.subprocess, "run", fake_run)
    monkeypatch.setattr(desktop.sys, "platform", "darwin")
    desktop.export(tmp_path / "in.drawio", tmp_path / "out.png", fmt="png", page=1, scale=2)
    command = calls[0]
    assert command[0] == str(exe) and "--export" in command
    assert command[command.index("--page-index") + 1] == "2"
    assert command[command.index("--scale") + 1] == "2"


def test_scene_handles_loaded_files_with_edge_label_children():
    xml = """<mxfile><diagram id="d" name="D"><mxGraphModel><root>
      <mxCell id="0"/><mxCell id="1" parent="0"/>
      <mxCell id="a" value="A" style="rounded=1;whiteSpace=wrap;html=1;" vertex="1" parent="1">
        <mxGeometry x="0" y="0" width="100" height="40" as="geometry"/></mxCell>
      <mxCell id="b" value="B" style="ellipse;" vertex="1" parent="1">
        <mxGeometry x="300" y="0" width="100" height="40" as="geometry"/></mxCell>
      <mxCell id="e" style="edgeStyle=orthogonalEdgeStyle;" edge="1" parent="1" source="a" target="b">
        <mxGeometry relative="1" as="geometry"/></mxCell>
      <mxCell id="l" value="calls" style="edgeLabel;html=1;" vertex="1" connectable="0" parent="e">
        <mxGeometry x="-0.5" relative="1" as="geometry"><mxPoint as="offset"/></mxGeometry></mxCell>
    </root></mxGraphModel></diagram></mxfile>"""
    scene = build(Document.from_xml(xml).pages[0])
    assert [s.kind for s in scene.shapes] == ["rectangle", "ellipse"]
    connector = scene.connectors[0]
    assert connector.labels[0].text == "calls"
    assert connector.labels[0].box[0] < 200  # placed toward the source (x=-0.5)


def test_intended_overlaps_are_not_reported():
    doc = Document()
    page = doc.add_page("Intended")
    # A balance factor in a white box beside a round node: only bounding boxes touch.
    page.ellipse("44", 232, 40, 64, 64)
    page.box("+2", 286, 6, 62, 42, style={"fillColor": "#ffffff", "strokeColor": "#ffffff"})
    # A sequence diagram: thin lifelines under a fragment frame, a message across them.
    a = page.box("Client", 400, 0, 100, 40)
    b = page.box("Server", 700, 0, 100, 40)
    page.box("", 445, 40, 10, 400, id="life-a")
    page.box("", 745, 40, 10, 400, id="life-b")
    page.box("", 380, 150, 460, 120, id="frame", style={"dashed": 1, "fillColor": "#fdeeec"})
    page.box("Touching", 0, 300, 100, 50)
    page.box("Neighbour", 100, 300, 100, 50)
    page.connect(a, b, waypoints=[(600, 200)])
    assert check(doc) == []


def test_real_overlaps_with_round_shapes_are_reported():
    doc = Document()
    page = doc.add_page("Real")
    page.ellipse("A", 0, 0, 100, 100)
    page.box("B", 40, 40, 100, 100)
    assert codes(doc) == ["overlap"]
