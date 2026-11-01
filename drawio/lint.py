"""Layout checks: what `validate` cannot see because the XML is well formed.

Each finding names the cells involved, says what is wrong in words an agent can act on,
and carries the numbers behind it. Text sizes come from drawio.text and connector routes
from drawio.scene, so findings are estimates: a clean report means nothing obviously
collides, not that the picture is pixel-perfect.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Optional

from .scene import Box, Connector, Label, Scene, Shape, build

SEVERITIES = ("error", "warning", "info")


@dataclass
class Issue:
    code: str
    severity: str
    page: str
    cells: list[str]
    message: str
    hint: str = ""
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Fit:
    """Where the picture will be placed, to judge the size text ends up at."""

    width: float
    height: Optional[float] = None
    unit: str = "in"  # in, cm, mm, pt or px
    min_pt: float = 12

    def points(self, value: float) -> float:
        return value * {"in": 72, "cm": 72 / 2.54, "mm": 72 / 25.4, "pt": 1, "px": 0.75}[self.unit]


def parse_fit(spec: str, min_pt: float = 12) -> Fit:
    """Read '8.15x4.85in', '16cm', '1200x800px' and similar."""
    spec = spec.strip().lower()
    unit = "in"
    for suffix in ("in", "cm", "mm", "pt", "px"):
        if spec.endswith(suffix):
            unit, spec = suffix, spec[: -len(suffix)]
            break
    parts = spec.split("x")
    try:
        width = float(parts[0])
        height = float(parts[1]) if len(parts) > 1 and parts[1] else None
    except ValueError as exc:
        raise ValueError(f"Cannot read size {spec!r}; use e.g. 8.15x4.85in or 16cm") from exc
    if width <= 0 or (height is not None and height <= 0) or len(parts) > 2:
        raise ValueError(f"Cannot read size {spec!r}; use e.g. 8.15x4.85in or 16cm")
    return Fit(width, height, unit, min_pt)


def _area(a: Box, b: Box) -> float:
    w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def _inside(inner: Box, outer: Box, slack: float = 0.5) -> bool:
    return (
        inner[0] >= outer[0] - slack
        and inner[1] >= outer[1] - slack
        and inner[0] + inner[2] <= outer[0] + outer[2] + slack
        and inner[1] + inner[3] <= outer[1] + outer[3] + slack
    )


def _shrink(box: Box, by: float) -> Box:
    return box[0] + by, box[1] + by, max(box[2] - 2 * by, 0), max(box[3] - 2 * by, 0)


def _overlap_size(a: Box, b: Box) -> tuple[float, float]:
    w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return max(w, 0.0), max(h, 0.0)


_ROUND = ("ellipse", "doubleEllipse", "rhombus")


def _touches_outline(rect: Box, shape_box: Box, kind: str) -> bool:
    """Whether a rectangle reaches inside an ellipse or rhombus, not only its bounding box."""
    x, y, w, h = shape_box
    if kind not in _ROUND or w <= 0 or h <= 0:
        return True
    cx, cy, rx, ry = x + w / 2, y + h / 2, w / 2, h / 2
    px = min(max(cx, rect[0]), rect[0] + rect[2])
    py = min(max(cy, rect[1]), rect[1] + rect[3])
    dx, dy = abs(px - cx) / rx, abs(py - cy) / ry
    reach = dx + dy if kind == "rhombus" else dx * dx + dy * dy
    return reach < 0.98


def _collide(a: Box, a_kind: str, b: Box, b_kind: str) -> bool:
    w, h = _overlap_size(a, b)
    if w < 2 or h < 2:
        return False  # touching edges, not overlapping
    if a_kind in _ROUND and b_kind in _ROUND:
        # Sample one outline against the other.
        x, y, bw, bh = a
        points = [
            (
                x + bw / 2 + bw / 2 * math.cos(t / 8 * math.pi),
                y + bh / 2 + bh / 2 * math.sin(t / 8 * math.pi),
            )
            for t in range(16)
        ]
        return any(_touches_outline((px, py, 0, 0), b, b_kind) for px, py in points) or (
            _touches_outline((b[0] + b[2] / 2, b[1] + b[3] / 2, 0, 0), a, a_kind)
        )
    return _touches_outline(a, b, b_kind) and _touches_outline(b, a, a_kind)


def _segment_hits(a, b, box: Box) -> bool:
    """Whether segment a-b passes through the interior of box (Liang-Barsky)."""
    x0, y0 = a
    dx, dy = b[0] - x0, b[1] - y0
    t0, t1 = 0.0, 1.0
    for p, q in (
        (-dx, x0 - box[0]),
        (dx, box[0] + box[2] - x0),
        (-dy, y0 - box[1]),
        (dy, box[1] + box[3] - y0),
    ):
        if p == 0:
            if q < 0:
                return False
        else:
            t = q / p
            if p < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
    return t0 < t1 and (t1 - t0) * math.hypot(dx, dy) > 1


def _round(box: Box) -> list[float]:
    return [round(v, 1) for v in box]


def _label_area(shape: Shape) -> Box:
    style = shape.style
    x, y, w, h = shape.box

    def num(key: str, default: float = 0) -> float:
        try:
            return float(style.get(key, default))
        except (TypeError, ValueError):
            return default

    spacing = num("spacing", 2)
    left, right = spacing + num("spacingLeft"), spacing + num("spacingRight")
    top, bottom = spacing + num("spacingTop"), spacing + num("spacingBottom")
    if shape.kind == "swimlane":
        return x + left, y + top, w - left - right, num("startSize", 23) - top - bottom
    return x + left, y + top, w - left - right, h - top - bottom


def check_scene(scene: Scene, fit: Optional[Fit] = None) -> list[Issue]:
    issues: list[Issue] = []
    page = scene.page_id
    shapes = scene.shapes
    by_id = {s.id: s for s in shapes}

    def ancestors(id: Optional[str]) -> set[str]:
        out: set[str] = set()
        while id in by_id and id not in out:
            out.add(id)
            id = by_id[id].parent
        return out

    lineage = {s.id: ancestors(s.parent) for s in shapes}
    background = (scene.background or "#ffffff").lower()

    def invisible(color: Optional[str]) -> bool:
        return color is None or color.lower() in ("none", background)

    # Text cells, and boxes drawn in the page colour to look like text, are judged by the
    # text they show rather than by their (invisible) box.
    textlike = {
        s.id
        for s in shapes
        if s.kind == "text"
        or (
            s.kind in ("rectangle", "label")
            and invisible(s.style.get("fillColor", "#ffffff"))
            and invisible(s.style.get("strokeColor", "#000000"))
        )
    }

    def footprint(shape: Shape) -> Box:
        if shape.id in textlike:
            return shape.label.box if shape.label else (shape.box[0], shape.box[1], 0, 0)
        return shape.box

    def kind(shape: Shape) -> str:
        return "text" if shape.id in textlike else shape.kind

    # Thin unlabeled bars (lifelines, separators, rules) behave like lines: messages cross
    # them and frames cover them on purpose.
    bars = {
        s.id
        for s in shapes
        if not (s.label and s.label.text.strip())
        and min(s.box[2], s.box[3]) <= 12
        and max(s.box[2], s.box[3]) >= 8 * max(min(s.box[2], s.box[3]), 1)
    }
    solid = [s for s in shapes if s.id not in textlike]
    # A shape that encloses other shapes is a backdrop drawn to group them, whether or not
    # it is a draw.io container: shapes on it and connectors across it are intended.
    backdrops = {
        s.id
        for s in solid
        if s.container or any(o is not s and _inside(o.box, s.box) for o in solid)
    }

    def related(a: str, b: str) -> bool:
        return a in lineage.get(b, ()) or b in lineage.get(a, ())

    # Labels that cross the outline of their shape.
    for shape in shapes:
        label = shape.label
        if label is None or shape.id in textlike:
            continue
        if shape.style.get("verticalLabelPosition") in ("bottom", "top"):
            continue
        box = _label_area(shape) if shape.kind == "swimlane" else _shrink(shape.box, 1)
        need_w = label.box[2] - box[2]
        need_h = label.box[3] - box[3]
        if need_w > 1 or need_h > 1:
            area = _label_area(shape)
            grow_w = shape.box[2] + max(label.box[2] - area[2], 0)
            grow_h = shape.box[3] + max(label.box[3] - area[3], 0)
            issues.append(
                Issue(
                    "text-overflow",
                    "warning",
                    page,
                    [shape.id],
                    f"Label {_quote(label.text)} needs {label.box[2]:.0f}x{label.box[3]:.0f}"
                    f" and runs past the edge of its {shape.box[2]:.0f}x{shape.box[3]:.0f}"
                    " shape.",
                    f"Resize to at least {math.ceil(grow_w)}x{math.ceil(grow_h)}, shorten the"
                    " label, lower fontSize, or call page.autosize(cell).",
                    {"label": _round(label.box), "shape": _round(shape.box)},
                )
            )

    # Shapes on top of each other.
    for i, a in enumerate(shapes):
        for b in shapes[i + 1 :]:
            if related(a.id, b.id) or a.id in bars or b.id in bars:
                continue
            fa, fb = footprint(a), footprint(b)
            if not _collide(fa, kind(a), fb, kind(b)):
                continue
            overlap = _area(fa, fb)
            a_text, b_text = a.id in textlike, b.id in textlike
            if (a.id in backdrops and _inside(fb, a.box)) or (
                b.id in backdrops and _inside(fa, b.box)
            ):
                continue
            if a_text != b_text:
                text, other = (a, b) if a_text else (b, a)
                if _inside(footprint(text), other.box) or other.container:
                    continue  # a caption placed on a shape
                code = "text-overlap"
            elif a.container and b.container:
                code = "container-overlap"
            elif a.container or b.container:
                inner = b if a.container else a
                outer = a if a.container else b
                if _inside(inner.box, outer.box):
                    code = "shape-in-foreign-container"
                else:
                    code = "overlap"
            else:
                code = "overlap"
            issues.append(
                Issue(
                    code,
                    "warning",
                    page,
                    [a.id, b.id],
                    f"{_name(a)} and {_name(b)} overlap by {overlap:.0f} px².",
                    "Move one of them, or put a shape that belongs inside a container in it"
                    " with parent=.",
                    {"a": _round(fa), "b": _round(fb)},
                )
            )

    # Children outside their container.
    for shape in shapes:
        parent = by_id.get(shape.parent) if shape.parent else None
        if parent is not None and not _inside(shape.box, parent.box):
            issues.append(
                Issue(
                    "outside-parent",
                    "warning",
                    page,
                    [shape.id, parent.id],
                    f"{_name(shape)} sticks out of its container {_name(parent)}.",
                    "Grow the container (page.fit(container)) or move the child.",
                    {"child": _round(shape.box), "parent": _round(parent.box)},
                )
            )

    connectors = scene.connectors
    depth = {item.id: i for i, item in enumerate(scene.items)}  # drawing order
    for edge in connectors:
        ends = {edge.source, edge.target}
        allowed = set()
        for end in ends:
            if end:
                allowed |= {end} | lineage.get(end, set())
        for shape in shapes:
            if shape.id in allowed or shape.id in backdrops or shape.id in bars:
                continue
            if not (shape.label and shape.label.text.strip()) and depth[shape.id] < depth[edge.id]:
                continue  # an unlabeled shape under the connector is a frame or a backdrop
            target = footprint(shape)
            if shape.kind in _ROUND:  # stay clear of the empty corners of the bounding box
                target = _shrink(target, min(target[2], target[3]) * 0.15)
            if any(
                _segment_hits(a, b, _shrink(target, 1))
                for a, b in zip(edge.points, edge.points[1:])
            ):
                code = "edge-crosses-label" if shape.id in textlike else "edge-crosses-shape"
                issues.append(
                    Issue(
                        code,
                        "warning",
                        page,
                        [edge.id, shape.id],
                        f"Connector {edge.id} runs through {_name(shape)}.",
                        "Add waypoints that go around it, set source_port/target_port, or move"
                        " the shape out of the way.",
                        {"route": [list(p) for p in edge.points], "shape": _round(shape.box)},
                    )
                )
        for other in connectors:
            if other is edge:
                continue
            for label in other.labels:
                if any(
                    _segment_hits(a, b, _shrink(label.box, 1))
                    for a, b in zip(edge.points, edge.points[1:])
                ):
                    issues.append(
                        Issue(
                            "edge-crosses-label",
                            "warning",
                            page,
                            [edge.id, other.id],
                            f"Connector {edge.id} runs through the label"
                            f" {_quote(label.text)} of {other.id}.",
                            "Move the label (a separate text cell, or a shorter label) or reroute"
                            " one connector with waypoints.",
                            {"route": [list(p) for p in edge.points], "label": _round(label.box)},
                        )
                    )

    # Connector labels sitting on shapes or on each other.
    labels = [(edge, label) for edge in connectors for label in edge.labels]
    for edge, label in labels:
        for shape in shapes:
            if shape.id in backdrops or shape.id in bars or shape.id in (edge.source, edge.target):
                continue
            if _collide(label.box, "text", footprint(shape), kind(shape)):
                issues.append(
                    Issue(
                        "label-overlap",
                        "warning",
                        page,
                        [edge.id, shape.id],
                        f"The label {_quote(label.text)} of {edge.id} covers {_name(shape)}.",
                        "Lengthen or reroute the connector, or shorten the label.",
                        {"label": _round(label.box), "shape": _round(shape.box)},
                    )
                )
    for i, (edge, label) in enumerate(labels):
        for other, other_label in labels[i + 1 :]:
            if _collide(label.box, "text", other_label.box, "text"):
                issues.append(
                    Issue(
                        "label-overlap",
                        "warning",
                        page,
                        [edge.id, other.id],
                        f"Labels {_quote(label.text)} and {_quote(other_label.text)} overlap.",
                        "Spread the connectors apart or move one label.",
                        {"a": _round(label.box), "b": _round(other_label.box)},
                    )
                )

    # Connectors drawn on top of each other.
    for i, edge in enumerate(connectors):
        for other in connectors[i + 1 :]:
            if edge.source == other.source or edge.target == other.target:
                continue  # a shared trunk out of, or into, one shape is drawn on purpose
            shared = _shared_run(edge.points, other.points)
            if shared > 10:
                issues.append(
                    Issue(
                        "edges-overlap",
                        "warning",
                        page,
                        [edge.id, other.id],
                        f"Connectors {edge.id} and {other.id} run on top of each other for"
                        f" {shared:.0f} px.",
                        "Give them different ports or waypoints so both stay visible.",
                    )
                )

    for shape in shapes:
        if not shape.known:
            issues.append(
                Issue(
                    "unsupported-shape",
                    "info",
                    page,
                    [shape.id],
                    f"The native renderer draws shape {shape.kind!r} as a rectangle.",
                    "draw.io shows it correctly; use --backend desktop or browser to export it.",
                )
            )

    if fit is not None:
        issues.extend(_fit_issues(scene, fit))
    return issues


def _shared_run(a_points, b_points) -> float:
    total = 0.0
    for a0, a1 in zip(a_points, a_points[1:]):
        for b0, b1 in zip(b_points, b_points[1:]):
            if abs(a0[0] - a1[0]) < 0.5 and abs(b0[0] - b1[0]) < 0.5 and abs(a0[0] - b0[0]) < 2:
                lo = max(min(a0[1], a1[1]), min(b0[1], b1[1]))
                hi = min(max(a0[1], a1[1]), max(b0[1], b1[1]))
                total += max(0.0, hi - lo)
            elif abs(a0[1] - a1[1]) < 0.5 and abs(b0[1] - b1[1]) < 0.5 and abs(a0[1] - b0[1]) < 2:
                lo = max(min(a0[0], a1[0]), min(b0[0], b1[0]))
                hi = min(max(a0[0], a1[0]), max(b0[0], b1[0]))
                total += max(0.0, hi - lo)
    return total


def _fit_issues(scene: Scene, fit: Fit) -> list[Issue]:
    issues = []
    x, y, w, h = scene.bounds()
    if w <= 0 or h <= 0:
        return issues
    box_w = fit.points(fit.width)
    scale = box_w / w
    if fit.height:
        box_h = fit.points(fit.height)
        scale = min(scale, box_h / h)
        ratio, wanted = w / h, fit.width / fit.height
        if abs(ratio - wanted) / wanted > 0.05:
            issues.append(
                Issue(
                    "aspect",
                    "info",
                    scene.page_id,
                    [],
                    f"The page is {ratio:.2f}:1 but the target box is {wanted:.2f}:1, so a"
                    " picture fitted into it leaves bands, or is cropped by slide tools that fill"
                    " the box.",
                    f"Render with --aspect {fit.width}:{fit.height} to pad the canvas, or reshape"
                    " the layout.",
                    {"page_ratio": round(ratio, 3), "box_ratio": round(wanted, 3)},
                )
            )
    labels: list[tuple[str, Label]] = [(s.id, s.label) for s in scene.shapes if s.label]
    labels += [(e.id, label) for e in scene.connectors for label in e.labels]
    small = [(id, label, label.font_size * scale) for id, label in labels]
    small = [item for item in small if item[2] < fit.min_pt]
    if small:
        smallest = min(item[2] for item in small)
        needed = max(item[1].font_size * fit.min_pt / item[2] for item in small)
        issues.append(
            Issue(
                "small-text",
                "warning",
                scene.page_id,
                [item[0] for item in small],
                f"{len(small)} label(s) end up below {fit.min_pt:g} pt once the page is scaled"
                f" into {fit.width:g}{fit.unit}; the smallest is {smallest:.1f} pt.",
                f"Raise fontSize to about {math.ceil(needed)} (Theme(font_size=...)), or make the"
                " diagram narrower so it is scaled down less.",
                {"scale": round(scale, 4), "smallest_pt": round(smallest, 2)},
            )
        )
    return issues


def _quote(text: str) -> str:
    text = " ".join(text.split())
    return repr(text if len(text) <= 40 else text[:37] + "...")


def _name(shape: Shape) -> str:
    if shape.label and shape.label.text.strip():
        return f"{shape.id} {_quote(shape.label.text)}"
    return shape.id


def check(document, *, fit: Optional[Fit] = None, pages=None) -> list[Issue]:
    """Run every layout check on a Document (or only on the pages whose IDs are given)."""
    result = []
    for page in document.pages:
        if pages and page.id not in pages and page.name not in pages:
            continue
        result.extend(check_scene(build(page), fit))
    return result


__all__ = ["Connector", "Fit", "Issue", "check", "check_scene", "parse_fit"]
