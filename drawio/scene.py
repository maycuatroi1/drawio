"""Where everything on a page ends up: absolute boxes, label boxes and connector routes.

The renderer, the layout checks and `drawio inspect` all read a page through this
module, so they agree with each other. Connector routes follow draw.io's orthogonal and
straight edge styles closely for the common cases (ports, waypoints, side-by-side or
stacked shapes); they are an approximation of draw.io's router, not a copy of it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from . import text as metrics
from .document import Page, parse_style

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


def _side_point(box: Box, side: str, at: Optional[float] = None) -> Point:
    x, y, w, h = box
    if side == "left":
        return x, at if at is not None else y + h / 2
    if side == "right":
        return x + w, at if at is not None else y + h / 2
    if side == "top":
        return at if at is not None else x + w / 2, y
    return at if at is not None else x + w / 2, y + h


_NORMAL = {"left": (-1, 0), "right": (1, 0), "top": (0, -1), "bottom": (0, 1)}


def _port(box: Box, fx: float, fy: float, kind: str = "rectangle") -> tuple[Point, str]:
    x, y, w, h = box
    point = (x + fx * w, y + fy * h)
    distances = {"left": fx, "right": 1 - fx, "top": fy, "bottom": 1 - fy}
    side = min(distances, key=distances.get)
    return _onto_outline(box, point, side, kind), side


def _onto_outline(box: Box, point: Point, side: str, kind: str) -> Point:
    """Move a port on the bounding box inward, along the side's normal, to the outline of
    an ellipse or rhombus, as draw.io's perimeters do."""
    x, y, w, h = box
    if kind not in ("ellipse", "doubleEllipse", "rhombus") or w <= 0 or h <= 0:
        return point
    cx, cy = x + w / 2, y + h / 2
    rx, ry = w / 2, h / 2
    if side in ("top", "bottom"):
        u = min(1.0, abs(point[0] - cx) / rx)
        reach = math.sqrt(1 - u * u) if kind != "rhombus" else 1 - u
        return point[0], cy + (ry * reach if side == "bottom" else -ry * reach)
    v = min(1.0, abs(point[1] - cy) / ry)
    reach = math.sqrt(1 - v * v) if kind != "rhombus" else 1 - v
    return cx + (rx * reach if side == "right" else -rx * reach), point[1]


def _facing(box: Box, toward: Point) -> str:
    """The side of box that faces a point."""
    x, y, w, h = box
    cx, cy = _centre(box)
    dx, dy = toward[0] - cx, toward[1] - cy
    if x <= toward[0] <= x + w and not (y <= toward[1] <= y + h):
        return "bottom" if dy > 0 else "top"
    if y <= toward[1] <= y + h and not (x <= toward[0] <= x + w):
        return "right" if dx > 0 else "left"
    if abs(dx) * h >= abs(dy) * w:
        return "right" if dx > 0 else "left"
    return "bottom" if dy > 0 else "top"


def _endpoint(box: Box, toward: Point) -> tuple[Point, str]:
    """Where a connector without a port leaves a box heading for `toward`."""
    side = _facing(box, toward)
    x, y, w, h = box
    if side in ("left", "right") and y <= toward[1] <= y + h:
        return _side_point(box, side, toward[1]), side
    if side in ("top", "bottom") and x <= toward[0] <= x + w:
        return _side_point(box, side, toward[0]), side
    return _side_point(box, side), side


def _simplify(points: list[Point]) -> list[Point]:
    out: list[Point] = []
    for p in points:
        p = (round(p[0], 2), round(p[1], 2))
        if out and abs(out[-1][0] - p[0]) < 0.01 and abs(out[-1][1] - p[1]) < 0.01:
            continue
        if len(out) >= 2:
            a, b = out[-2], out[-1]
            if (abs(a[0] - b[0]) < 0.01 and abs(b[0] - p[0]) < 0.01) or (
                abs(a[1] - b[1]) < 0.01 and abs(b[1] - p[1]) < 0.01
            ):
                out[-1] = p
                continue
        out.append(p)
    return out


def _elbow(a: Point, a_side: str, b: Point, b_side: str) -> list[Point]:
    """Orthogonal path from a (leaving through a_side) to b (entering through b_side)."""
    stub = 20.0
    ax, ay = a[0] + _NORMAL[a_side][0] * stub, a[1] + _NORMAL[a_side][1] * stub
    bx, by = b[0] + _NORMAL[b_side][0] * stub, b[1] + _NORMAL[b_side][1] * stub
    a_horizontal = a_side in ("left", "right")
    b_horizontal = b_side in ("left", "right")
    forward_a = (bx - a[0]) * _NORMAL[a_side][0] + (by - a[1]) * _NORMAL[a_side][1] > 0
    if a_horizontal and b_horizontal:
        if forward_a and (a[0] - b[0]) * _NORMAL[b_side][0] > 0:
            mid = (a[0] + b[0]) / 2
            return [a, (mid, a[1]), (mid, b[1]), b]
        return [a, (ax, a[1]), (ax, (a[1] + b[1]) / 2), (bx, (a[1] + b[1]) / 2), (bx, b[1]), b]
    if not a_horizontal and not b_horizontal:
        if forward_a and (a[1] - b[1]) * _NORMAL[b_side][1] > 0:
            mid = (a[1] + b[1]) / 2
            return [a, (a[0], mid), (b[0], mid), b]
        return [a, (a[0], ay), ((a[0] + b[0]) / 2, ay), ((a[0] + b[0]) / 2, by), (b[0], by), b]
    if a_horizontal:
        return [a, (b[0], a[1]), b] if forward_a else [a, (ax, a[1]), (ax, by), (b[0], by), b]
    return [a, (a[0], b[1]), b] if forward_a else [a, (a[0], ay), (bx, ay), (bx, b[1]), b]


def _orthogonal(points: list[Point], heading_horizontal: bool) -> list[Point]:
    """Insert corners so that consecutive points are joined by axis-aligned segments."""
    out = [points[0]]
    horizontal = heading_horizontal
    for p in points[1:]:
        q = out[-1]
        if abs(q[0] - p[0]) > 0.01 and abs(q[1] - p[1]) > 0.01:
            out.append((p[0], q[1]) if horizontal else (q[0], p[1]))
            horizontal = not horizontal
        elif abs(q[1] - p[1]) <= 0.01:
            horizontal = True
        else:
            horizontal = False
        out.append(p)
    return out


def _perimeter(box: Box, toward: Point, kind: str) -> Point:
    """Where a straight line from the box centre to `toward` crosses the outline."""
    cx, cy = _centre(box)
    dx, dy = toward[0] - cx, toward[1] - cy
    if dx == 0 and dy == 0:
        return cx, cy
    w, h = box[2] / 2, box[3] / 2
    if kind in ("ellipse", "doubleEllipse") and w > 0 and h > 0:
        t = 1 / math.sqrt((dx / w) ** 2 + (dy / h) ** 2)
    else:
        tx = w / abs(dx) if dx else math.inf
        ty = h / abs(dy) if dy else math.inf
        t = min(tx, ty)
    return cx + dx * t, cy + dy * t


def route(
    source: Optional[Box],
    target: Optional[Box],
    style: dict,
    waypoints: list[Point],
    source_point: Optional[Point] = None,
    target_point: Optional[Point] = None,
    source_kind: str = "rectangle",
    target_kind: str = "rectangle",
) -> list[Point]:
    """Approximate the path draw.io draws for a connector."""
    edge_style = style.get("edgeStyle", "none")
    exit_port = entry_port = None
    if source and "exitX" in style and "exitY" in style:
        exit_port = _port(source, _num(style, "exitX", 0.5), _num(style, "exitY", 0.5), source_kind)
    if target and "entryX" in style and "entryY" in style:
        entry_port = _port(
            target, _num(style, "entryX", 0.5), _num(style, "entryY", 0.5), target_kind
        )

    def far_end(box: Optional[Box], point: Optional[Point]) -> Point:
        return _centre(box) if box else (point or (0.0, 0.0))

    if edge_style in ("none", "") or edge_style is None:
        first = waypoints[0] if waypoints else far_end(target, target_point)
        last = waypoints[-1] if waypoints else far_end(source, source_point)
        if exit_port:
            start = exit_port[0]
        elif source:
            start = _perimeter(source, first, source_kind)
        else:
            start = source_point or (0.0, 0.0)
        if entry_port:
            end = entry_port[0]
        elif target:
            end = _perimeter(target, last, target_kind)
        else:
            end = target_point or (0.0, 0.0)
        return _simplify([start, *waypoints, end])

    # Orthogonal family: orthogonalEdgeStyle, elbowEdgeStyle, entityRelationEdgeStyle...
    if not waypoints:
        if exit_port and entry_port:
            return _simplify(_elbow(exit_port[0], exit_port[1], entry_port[0], entry_port[1]))
        if source and target:
            sx, sy, sw, sh = source
            tx, ty, tw, th = target
            if exit_port:
                end, side = _endpoint(target, exit_port[0])
                return _simplify(_elbow(exit_port[0], exit_port[1], end, side))
            if entry_port:
                start, side = _endpoint(source, entry_port[0])
                return _simplify(_elbow(start, side, entry_port[0], entry_port[1]))
            overlap_x = min(sx + sw, tx + tw) - max(sx, tx)
            overlap_y = min(sy + sh, ty + th) - max(sy, ty)
            if overlap_x > 0 and (ty >= sy + sh or sy >= ty + th):
                mx = max(sx, tx) + overlap_x / 2
                if ty >= sy + sh:
                    return [(mx, sy + sh), (mx, ty)]
                return [(mx, sy), (mx, ty + th)]
            if overlap_y > 0 and (tx >= sx + sw or sx >= tx + tw):
                my = max(sy, ty) + overlap_y / 2
                if tx >= sx + sw:
                    return [(sx + sw, my), (tx, my)]
                return [(sx, my), (tx + tw, my)]
            (scx, scy), (tcx, tcy) = _centre(source), _centre(target)
            if abs(tcx - scx) >= abs(tcy - scy):
                a_side = "right" if tcx > scx else "left"
                b_side = "left" if tcx > scx else "right"
            else:
                a_side = "bottom" if tcy > scy else "top"
                b_side = "top" if tcy > scy else "bottom"
            return _simplify(
                _elbow(_side_point(source, a_side), a_side, _side_point(target, b_side), b_side)
            )
    first = waypoints[0] if waypoints else far_end(target, target_point)
    last = waypoints[-1] if waypoints else far_end(source, source_point)
    if exit_port:
        start, start_side = exit_port
    elif source:
        start, start_side = _endpoint(source, first)
    else:
        start = source_point or (0.0, 0.0)
        start_side = "right" if first[0] >= start[0] else "left"
    if entry_port:
        end, end_side = entry_port
    elif target:
        end, end_side = _endpoint(target, last)
    else:
        end = target_point or (0.0, 0.0)
        end_side = "left" if last[0] <= end[0] else "right"
    path = _orthogonal([start, *waypoints], start_side in ("left", "right"))
    tail = path[-1]
    if abs(tail[0] - end[0]) > 0.01 and abs(tail[1] - end[1]) > 0.01:
        # Enter the target through end_side, as draw.io does.
        if end_side in ("left", "right"):
            path.append((tail[0], end[1]))
        else:
            path.append((end[0], tail[1]))
    path.append(end)
    return _simplify(path)


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
    scene = Scene(page.id, page.name, page.model.get("background") or "#ffffff")
    edge_labels: dict[str, list[tuple]] = {}
    children: dict[Optional[str], list[str]] = {}
    for id, cell in index.items():
        children.setdefault(cell.get("parent"), []).append(id)

    for id, cell in index.items():
        style = parse_style(cell.get("style"))
        kinds[id] = shape_kind(style)
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
            scene.items.append(_connector(page, id, cell, style, boxes, kinds, edge_labels))
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
