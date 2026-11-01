import pytest

from drawio import Document
from drawio import text as metrics
from drawio.layout import column, grid, layered, row


def tree():
    page = Document().add_page("T")
    root = page.box("root", 0, 0, 120, 50, id="root")
    kids = [page.box(f"k{i}", 0, 0, 100, 40, id=f"k{i}") for i in range(3)]
    for kid in kids:
        page.connect(root, kid)
    leaves = [page.box(f"l{i}", 0, 0, 80, 40, id=f"l{i}") for i in range(2)]
    for leaf in leaves:
        page.connect(kids[0], leaf)
    return page, root, kids, leaves


def centre_x(cell):
    return cell.x + cell.width / 2


def test_layered_tree_ranks_and_centres_parents():
    page, root, kids, leaves = tree()
    layered(page, rank_gap=60, gap=30)
    assert root.y < kids[0].y < leaves[0].y
    assert len({k.y for k in kids}) == 1
    ordered = sorted(kids, key=lambda c: c.x)
    for a, b in zip(ordered, ordered[1:]):
        assert b.x >= a.x + a.width + 30 - 0.01
    assert centre_x(kids[0]) == pytest.approx((centre_x(leaves[0]) + centre_x(leaves[1])) / 2)
    edge = page.edges[0]
    assert edge.style["exitY"] == "1" and edge.style["entryY"] == "0"
    page.validate(check_bounds=True)


def test_layered_right_handles_cycles():
    page = Document().add_page("C")
    a, b, c = (page.box(n, 0, 0, 80, 40, id=n) for n in "abc")
    page.connect(a, b)
    page.connect(b, c)
    page.connect(c, a)
    layered(page, direction="right")
    assert a.x < b.x < c.x
    with pytest.raises(ValueError):
        layered(page, direction="diagonal")


def test_row_column_grid():
    page = Document().add_page("G")
    cells = [page.box(str(i), 0, 0, 50 + 10 * i, 30 + 10 * i) for i in range(4)]
    row(cells, x=10, y=10, gap=5)
    assert [c.x for c in cells] == [10, 65, 130, 205]
    assert cells[0].y == 10 + (60 - 30) / 2
    column(cells, x=0, y=0, gap=10, align="left")
    assert [c.y for c in cells] == [0, 40, 90, 150] and {c.x for c in cells} == {0}
    grid(cells, 2, x=0, y=0, gap=10)
    assert cells[2].y > cells[0].y and cells[1].x > cells[0].x
    with pytest.raises(ValueError):
        grid(cells, 0)


def test_text_metrics():
    assert metrics.text_width("Hello", 10) == pytest.approx(22.78, abs=0.01)
    assert metrics.text_width("Việt", 18) == metrics.text_width("Viet", 18)
    assert metrics.text_width("AB", 10, bold=True) > metrics.text_width("AB", 10)
    assert metrics.text_width("iii", 10, family="Courier New") == pytest.approx(18)
    lines = metrics.wrap("A plain label that is much too long", 140, 18)
    assert lines == ["A plain label that", "is much too long"]
    assert all(metrics.text_width(line, 18) <= 140 for line in lines)
    broken = metrics.wrap("Supercalifragilisticexpialidocious", 60, 12)
    assert len(broken) > 1 and "".join(broken) == "Supercalifragilisticexpialidocious"
    width, height, lines = metrics.measure("one\ntwo", 10)
    assert height == pytest.approx(24) and lines == ["one", "two"]
    assert metrics.plain("<b>A</b><br/>B &amp; C", html_label=True) == "A\nB & C"
