"""Where everything on a page ends up: absolute boxes, label boxes and connector routes.

The renderer, the layout checks and `drawio inspect` all read a page through this
module, so they agree with each other. Connector routes come from drawio.routing, a
port of draw.io's own routers, so they match what the editor draws.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from . import text as metrics
from .document import Page, parse_style
from .routing import route

Point = tuple[float, float]
Box = tuple[float, float, float, float]  # x, y, width, height

# Shape names the native renderer draws; anything else is drawn as a rectangle.
KNOWN_SHAPES = {
    "rectangle",
    "label",
    "ellipse",
    "doubleEllipse",
    "rhombus",
    "cylinder",
    "cylinder3",
    "hexagon",
    "triangle",
    "parallelogram",
    "document",
    "cloud",
    "process",
    "note",
    "card",
    "step",
    "umlActor",
    "actor",
    "image",
    "swimlane",
    "text",
    "line",
}
_NAMED_STYLES = {
    "ellipse",
    "doubleEllipse",
    "rhombus",
    "triangle",
    "swimlane",
    "text",
    "image",
    "line",
    "cloud",
    "hexagon",
}


@dataclass
class Label:
    text: str
    lines: list[str]
    box: Box  # where the text block sits
    font_size: float
    font_family: str
    font_color: str
    bold: bool
    italic: bool
    underline: bool
    align: str  # left, center, right
    background: Optional[str] = None


@dataclass
class Shape:
    id: str
    kind: str
    box: Box
    style: dict
    parent: Optional[str]
    container: bool
    label: Optional[Label] = None
    known: bool = True


@dataclass
class Connector:
    id: str
    points: list[Point]
    style: dict
    source: Optional[str]
    target: Optional[str]
    labels: list[Label] = field(default_factory=list)


@dataclass
class Scene:
    page_id: str
    name: str
    background: str
    items: list = field(default_factory=list)  # Shapes and Connectors in drawing order

    @property
    def shapes(self) -> list[Shape]:
        return [i for i in self.items if isinstance(i, Shape)]

    @property
    def connectors(self) -> list[Connector]:
        return [i for i in self.items if isinstance(i, Connector)]

    def bounds(self) -> Box:
        """Smallest box holding every shape, connector and label."""
        xs: list[float] = []
        ys: list[float] = []
        for item in self.items:
            boxes = []
            if isinstance(item, Shape):
                boxes.append(item.box)
                if item.label:
                    boxes.append(item.label.box)
            else:
                xs.extend(p[0] for p in item.points)
                ys.extend(p[1] for p in item.points)
                boxes.extend(label.box for label in item.labels)
            for x, y, w, h in boxes:
                xs += [x, x + w]
                ys += [y, y + h]
        if not xs:
            return 0.0, 0.0, 0.0, 0.0
        return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)


def _num(style: dict, key: str, default: float) -> float:
    try:
        return float(style.get(key, default))
    except (TypeError, ValueError):
        return default


def shape_kind(style: dict) -> str:
    shape = style.get("shape")
    if shape:
        return shape
    for name, value in style.items():
        if value is None and name in _NAMED_STYLES:
            return name
    return "rectangle"


def _is_text(style: dict, kind: str) -> bool:
    return kind == "text" or (
        style.get("fillColor", "none") == "none" and style.get("strokeColor") == "none"
    )


def _font(style: dict, default_size: float):
    size = _num(style, "fontSize", default_size)
    flags = int(_num(style, "fontStyle", 0))
    return (
        size,
        style.get("fontFamily", "Helvetica"),
        style.get("fontColor", "#000000"),
        bool(flags & 1),
        bool(flags & 2),
        bool(flags & 4),
    )


def _place(text: str, area: Box, style: dict, default_size: float, wrap: bool) -> Label:
    size, family, color, bold, italic, underline = _font(style, default_size)
    x, y, w, h = area
    width, height, lines = metrics.measure(
        text, size, width=max(w, 1) if wrap else None, bold=bold, family=family
    )
    align = style.get("align", "center")
    valign = style.get("verticalAlign", "middle")
    if align == "left":
        lx = x
    elif align == "right":
        lx = x + w - width
    else:
        lx = x + (w - width) / 2
    if valign == "top":
        ly = y
    elif valign == "bottom":
        ly = y + h - height
    else:
        ly = y + (h - height) / 2
    background = style.get("labelBackgroundColor")
    return Label(
        text,
        lines,
        (lx, ly, width, height),
        size,
        family,
        color,
        bold,
        italic,
        underline,
        align,
        None if background in (None, "none") else background,
    )


def _vertex_label(text: str, box: Box, style: dict, kind: str) -> Label:
    x, y, w, h = box
    spacing = _num(style, "spacing", 2)
    left = spacing + _num(style, "spacingLeft", 0)
    right = spacing + _num(style, "spacingRight", 0)
    top = spacing + _num(style, "spacingTop", 0)
    bottom = spacing + _num(style, "spacingBottom", 0)
    wrap = style.get("whiteSpace") == "wrap"
    position = style.get("verticalLabelPosition")
    if position == "bottom":
        area = (x + left, y + h + top, w - left - right, 0)
        style = {**style, "verticalAlign": "top"}
    elif position == "top":
        area = (x + left, y - bottom, w - left - right, 0)
        style = {**style, "verticalAlign": "bottom"}
    elif kind == "swimlane":
        start = _num(style, "startSize", 23)
        area = (x + left, y + top, w - left - right, start - top - bottom)
    else:
        if style.get("boundedLbl") == "1" and kind in ("cylinder3", "cylinder"):
            cap = _num(style, "size", 15)
            y, h = y + 2 * cap, h - 3 * cap
        area = (x + left, y + top, w - left - right, h - top - bottom)
    return _place(text, area, style, 12, wrap)


def _absolute(page: Page):
    """Absolute boxes of every vertex with absolute geometry, keyed by ID."""
    index = page._index()
    boxes: dict[str, Box] = {}

    def resolve(id: str, seen=()) -> Optional[Box]:
        if id in boxes:
            return boxes[id]
        cell = index.get(id)
        if cell is None or cell.get("vertex") != "1" or id in seen:
            return None
        geometry = cell.find("mxGeometry")
        if geometry is None or geometry.get("relative") == "1":
            return None
        x, y = float(geometry.get("x", "0")), float(geometry.get("y", "0"))
        w, h = float(geometry.get("width", "0")), float(geometry.get("height", "0"))
        parent = cell.get("parent")
        if parent in index and index[parent].get("vertex") == "1":
            origin = resolve(parent, (*seen, id))
            if origin is not None:
                x, y = x + origin[0], y + origin[1]
        boxes[id] = (x, y, w, h)
        return boxes[id]

    for id in index:
        resolve(id)
    return boxes


def _edge_origin(page: Page, parent: Optional[str], boxes: dict[str, Box]) -> Point:
    if parent in boxes:
        return boxes[parent][0], boxes[parent][1]
    return 0.0, 0.0


def _centre(box: Box) -> Point:
    return box[0] + box[2] / 2, box[1] + box[3] / 2


def perimeter_kind(style: dict, kind: str) -> str:
    """Which outline connectors attach to: draw.io's `perimeter` style, or the shape's own."""
    named = style.get("perimeter")
    if named == "ellipsePerimeter" or (named is None and kind in ("ellipse", "doubleEllipse")):
        return "ellipse"
    if named == "rhombusPerimeter" or (named is None and kind == "rhombus"):
        return "rhombus"
    return "rectangle"


def point_along(points: list[Point], fraction: float) -> Point:
    """The point at `fraction` (0..1) of a polyline's length."""
    lengths = [math.dist(a, b) for a, b in zip(points, points[1:])]
    total = sum(lengths)
    if total == 0:
        return points[0]
    goal = max(0.0, min(1.0, fraction)) * total
    for (a, b), length in zip(zip(points, points[1:]), lengths):
        if goal <= length and length > 0:
            t = goal / length
            return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        goal -= length
    return points[-1]


def _edge_label(text: str, points: list[Point], style: dict, position: float, offset: Point):
    x, y = point_along(points, (position + 1) / 2)
    size, family, *_ = _font(style, 11)
    wrap = style.get("whiteSpace") == "wrap"
    width, height, _ = metrics.measure(text, size, bold=_font(style, 11)[3], family=family)
    if wrap and width > 200:
        width = 200
    area = (x + offset[0] - width / 2, y + offset[1] - height / 2, width, height)
    label_style = {
        "labelBackgroundColor": "#ffffff",
        **style,
        "align": "center",
        "verticalAlign": "middle",
        "spacing": 0,
    }
    return _place(text, area, label_style, 11, wrap)


def build(page: Page) -> Scene:
    """Compute the scene of one page."""
    index = page._index()
    boxes = _absolute(page)
    kinds: dict[str, str] = {}
    outlines: dict[str, str] = {}
    scene = Scene(page.id, page.name, page.model.get("background") or "#ffffff")
    edge_labels: dict[str, list[tuple]] = {}
    children: dict[Optional[str], list[str]] = {}
    for id, cell in index.items():
        children.setdefault(cell.get("parent"), []).append(id)

    for id, cell in index.items():
        style = parse_style(cell.get("style"))
        kinds[id] = shape_kind(style)
        outlines[id] = perimeter_kind(style, kinds[id])
        parent = cell.get("parent")
        if (
            cell.get("vertex") == "1"
            and parent in index
            and index[parent].get("edge") == "1"
            and cell.get("value")
        ):
            geometry = cell.find("mxGeometry")
            offset = (0.0, 0.0)
            position = 0.0
            if geometry is not None:
                position = float(geometry.get("x", "0"))
                point = geometry.find("mxPoint[@as='offset']")
                if point is not None:
                    offset = (float(point.get("x", "0")), float(point.get("y", "0")))
            text = metrics.plain(cell.get("value", ""), html_label=style.get("html") == "1")
            edge_labels.setdefault(parent, []).append((text, style, position, offset))

    def emit(id: str) -> None:
        cell = index[id]
        style = parse_style(cell.get("style"))
        if cell.get("vertex") == "1" and id in boxes:
            kind = kinds[id]
            text = metrics.plain(cell.get("value", ""), html_label=style.get("html") == "1")
            if _is_text(style, kind) and kind not in ("image", "swimlane"):
                kind = "text"
            shape = Shape(
                id,
                kind,
                boxes[id],
                style,
                cell.get("parent"),
                style.get("container") == "1" or kind == "swimlane",
                _vertex_label(text, boxes[id], style, kind) if text.strip() else None,
                kind in KNOWN_SHAPES,
            )
            if style.get("visible") != "0":
                scene.items.append(shape)
        elif cell.get("edge") == "1":
            scene.items.append(_connector(page, id, cell, style, boxes, outlines, edge_labels))
        for child in children.get(id, []):
            emit(child)

    for top in children.get(None, []):
        emit(top)
    return scene


def _connector(page, id, cell, style, boxes, kinds, edge_labels) -> Connector:
    geometry = cell.find("mxGeometry")
    origin = _edge_origin(page, cell.get("parent"), boxes)
    waypoints: list[Point] = []
    source_point = target_point = None
    offset = (0.0, 0.0)
    position = 0.0
    if geometry is not None:
        for point in geometry.findall("Array[@as='points']/mxPoint"):
            waypoints.append(
                (float(point.get("x", "0")) + origin[0], float(point.get("y", "0")) + origin[1])
            )
        for attr in ("sourcePoint", "targetPoint"):
            point = geometry.find(f"mxPoint[@as='{attr}']")
            if point is not None:
                value = (
                    float(point.get("x", "0")) + origin[0],
                    float(point.get("y", "0")) + origin[1],
                )
                if attr == "sourcePoint":
                    source_point = value
                else:
                    target_point = value
        point = geometry.find("mxPoint[@as='offset']")
        if point is not None:
            offset = (float(point.get("x", "0")), float(point.get("y", "0")))
        position = float(geometry.get("x", "0") or 0)
    source, target = cell.get("source"), cell.get("target")
    points = route(
        boxes.get(source),
        boxes.get(target),
        style,
        waypoints,
        source_point,
        target_point,
        kinds.get(source, "rectangle"),
        kinds.get(target, "rectangle"),
    )
    connector = Connector(id, points, style, source, target)
    text = metrics.plain(cell.get("value", ""), html_label=style.get("html") == "1")
    if text.strip() and len(points) >= 2:
        connector.labels.append(_edge_label(text, points, style, position, offset))
    for label_text, label_style, label_position, label_offset in edge_labels.get(id, []):
        if len(points) >= 2:
            merged = {**style, **label_style}
            connector.labels.append(
                _edge_label(label_text, points, merged, label_position, label_offset)
            )
    return connector


def scenes(document) -> list[Scene]:
    return [build(page) for page in document.pages]
