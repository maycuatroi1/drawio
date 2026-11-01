"""Draw a page with no browser and no draw.io install.

The scene (drawio.scene) is turned into a short list of drawing primitives; one painter
writes them as SVG using only the standard library, another rasterises them with Pillow
for PNG, JPEG and PDF. Both draw the same primitives, so the two outputs agree.

Text is written as SVG <text>, never foreignObject, so the SVG converts cleanly with
rsvg-convert, Inkscape, cairosvg or a browser, and embeds in LaTeX, slides and PDFs.
"""

from __future__ import annotations

import base64
import io
import math
from dataclasses import dataclass
from typing import Optional
from xml.sax.saxutils import escape, quoteattr

from ..scene import Box, Connector, Label, Point, Scene, Shape
from ..text import LINE_HEIGHT


@dataclass
class Stroke:
    color: Optional[str]
    width: float = 1.0
    dash: Optional[tuple[float, ...]] = None
    opacity: float = 1.0


@dataclass
class Poly:
    points: list[Point]
    closed: bool
    fill: Optional[str]
    stroke: Stroke
    fill_opacity: float = 1.0


@dataclass
class Ellipse:
    cx: float
    cy: float
    rx: float
    ry: float
    fill: Optional[str]
    stroke: Stroke
    fill_opacity: float = 1.0


@dataclass
class Text:
    label: Label


@dataclass
class Picture:
    box: Box
    uri: str


def _num(style: dict, key: str, default: float) -> float:
    try:
        return float(style.get(key, default))
    except (TypeError, ValueError):
        return default


def _color(value: Optional[str], default: Optional[str]) -> Optional[str]:
    if value is None:
        return default
    if value in ("none", "", "default"):
        return None if value == "none" else default
    return value


def _stroke(style: dict, default_color: Optional[str] = "#000000") -> Stroke:
    width = _num(style, "strokeWidth", 1)
    dash = None
    if style.get("dashed") == "1":
        pattern = style.get("dashPattern")
        try:
            dash = tuple(float(v) * width for v in pattern.split()) if pattern else None
        except ValueError:
            dash = None
        dash = dash or (3 * width, 3 * width)
    opacity = _num(style, "opacity", 100) / 100 * _num(style, "strokeOpacity", 100) / 100
    return Stroke(_color(style.get("strokeColor"), default_color), width, dash, opacity)


def _arc(cx, cy, rx, ry, start, end, steps=24) -> list[Point]:
    return [
        (
            cx + rx * math.cos(start + (end - start) * i / steps),
            cy + ry * math.sin(start + (end - start) * i / steps),
        )
        for i in range(steps + 1)
    ]


def _rounded_rect(x, y, w, h, r) -> list[Point]:
    r = max(0.0, min(r, w / 2, h / 2))
    if r == 0:
        return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    pts: list[Point] = []
    pts += _arc(x + w - r, y + r, r, r, -math.pi / 2, 0, 6)
    pts += _arc(x + w - r, y + h - r, r, r, 0, math.pi / 2, 6)
    pts += _arc(x + r, y + h - r, r, r, math.pi / 2, math.pi, 6)
    pts += _arc(x + r, y + r, r, r, math.pi, 1.5 * math.pi, 6)
    return pts


def _size(style: dict, default: float, extent: float) -> float:
    """A shape's `size` property: a fraction of the extent unless fixedSize=1."""
    value = _num(style, "size", default)
    if style.get("fixedSize") == "1" or value > 1:
        return min(value, extent / 2)
    return value * extent


def _rotate(points: list[Point], box: Box, direction: str) -> list[Point]:
    """Turn an east-facing outline to face another direction within the same box."""
    x, y, w, h = box
    if direction == "west":
        return [(x + w - (px - x), py) for px, py in points]
    if direction in ("north", "south"):
        out = []
        for px, py in points:
            u, v = (px - x) / w if w else 0, (py - y) / h if h else 0
            out.append(
                (x + v * w, y + (1 - u) * h) if direction == "north" else (x + v * w, y + u * h)
            )
        return out
    return points


def shape_primitives(shape: Shape) -> list:
    style = shape.style
    x, y, w, h = shape.box
    kind = shape.kind
    fill_default = "#ffffff"
    fill = _color(style.get("fillColor"), fill_default)
    stroke = _stroke(style)
    fill_opacity = _num(style, "opacity", 100) / 100 * _num(style, "fillOpacity", 100) / 100
    out: list = []

    def poly(points, closed=True, f=fill, s=stroke):
        out.append(Poly(points, closed, f if closed else None, s, fill_opacity))

    if kind == "text":
        if fill or stroke.color:
            poly([(x, y), (x + w, y), (x + w, y + h), (x, y + h)])
    elif kind in ("ellipse", "doubleEllipse"):
        out.append(Ellipse(x + w / 2, y + h / 2, w / 2, h / 2, fill, stroke, fill_opacity))
        if kind == "doubleEllipse":
            inset = min(4 + stroke.width, w / 4, h / 4)
            out.append(Ellipse(x + w / 2, y + h / 2, w / 2 - inset, h / 2 - inset, None, stroke))
    elif kind == "rhombus":
        poly([(x + w / 2, y), (x + w, y + h / 2), (x + w / 2, y + h), (x, y + h / 2)])
    elif kind == "hexagon":
        s = _size(style, 0.25, w)
        poly(
            [
                (x + s, y),
                (x + w - s, y),
                (x + w, y + h / 2),
                (x + w - s, y + h),
                (x + s, y + h),
                (x, y + h / 2),
            ]
        )
    elif kind == "triangle":
        pts = [(x, y), (x + w, y + h / 2), (x, y + h)]
        poly(_rotate(pts, shape.box, style.get("direction", "east")))
    elif kind == "parallelogram":
        s = _size(style, 0.2, w)
        poly([(x + s, y), (x + w, y), (x + w - s, y + h), (x, y + h)])
    elif kind == "step":
        s = _size(style, 0.2, w)
        poly(
            [
                (x, y),
                (x + w - s, y),
                (x + w, y + h / 2),
                (x + w - s, y + h),
                (x, y + h),
                (x + s, y + h / 2),
            ]
        )
    elif kind == "document":
        dy = _num(style, "size", 0.3) * h
        wave = [
            (x + w - w * i / 24, y + h - dy / 2 + dy / 2 * math.sin(2 * math.pi * i / 24))
            for i in range(25)
        ]
        poly([(x, y), (x + w, y), *wave])
    elif kind in ("cylinder", "cylinder3"):
        dy = max(0.0, min(h / 2, _num(style, "size", 15)))
        top = _arc(x + w / 2, y + dy, w / 2, dy, math.pi, 2 * math.pi)
        bottom = _arc(x + w / 2, y + h - dy, w / 2, dy, 0, math.pi)
        poly([*top, *bottom])
        poly(_arc(x + w / 2, y + dy, w / 2, dy, 0, math.pi), closed=False)
    elif kind == "cloud":
        pts = []
        for i in range(73):
            t = 2 * math.pi * i / 72
            r = 1 + 0.07 * abs(math.sin(3.5 * t))
            pts.append(
                (
                    x + w / 2 + w / 2 * r * math.cos(t) / 1.07,
                    y + h / 2 + h / 2 * r * math.sin(t) / 1.07,
                )
            )
        poly(pts)
    elif kind == "process":
        poly([(x, y), (x + w, y), (x + w, y + h), (x, y + h)])
        s = _size(style, 0.1, w)
        poly([(x + s, y), (x + s, y + h)], closed=False)
        poly([(x + w - s, y), (x + w - s, y + h)], closed=False)
    elif kind == "note":
        s = min(_num(style, "size", 30), w / 2, h / 2)
        poly([(x, y), (x + w - s, y), (x + w, y + s), (x + w, y + h), (x, y + h)])
        poly([(x + w - s, y), (x + w - s, y + s), (x + w, y + s)], closed=False)
    elif kind == "card":
        s = min(_num(style, "size", 15), w / 2, h / 2)
        poly([(x + s, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y + s)])
    elif kind in ("umlActor", "actor"):
        head = min(w, h / 4)
        out.append(Ellipse(x + w / 2, y + head / 2, head / 2, head / 2, fill, stroke, fill_opacity))
        poly([(x + w / 2, y + head), (x + w / 2, y + h * 0.66)], closed=False)
        poly([(x, y + h * 0.4), (x + w, y + h * 0.4)], closed=False)
        poly([(x, y + h), (x + w / 2, y + h * 0.66), (x + w, y + h)], closed=False)
    elif kind == "image":
        uri = style.get("image")
        if uri:
            out.append(Picture(shape.box, uri))
        if stroke.color and style.get("strokeColor") not in (None, "none"):
            poly([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], f=None)
    elif kind == "line":
        poly([(x, y + h / 2), (x + w, y + h / 2)], closed=False)
    elif kind == "swimlane":
        start = min(_num(style, "startSize", 23), h)
        outline = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        body = _color(style.get("swimlaneFillColor"), None)
        if body:
            poly(outline, f=body, s=Stroke(None))
        poly([(x, y), (x + w, y), (x + w, y + start), (x, y + start)], s=Stroke(None))
        poly(outline, f=None)
        poly([(x, y + start), (x + w, y + start)], closed=False)
    else:
        radius = 0.0
        if style.get("rounded") == "1":
            if style.get("absoluteArcSize") == "1":
                radius = _num(style, "arcSize", 20) / 2
            else:
                radius = min(w, h) * _num(style, "arcSize", 15) / 100
        poly(_rounded_rect(x, y, w, h, radius))
    if shape.label is not None and style.get("noLabel") != "1":
        out.append(Text(shape.label))
    return out


_FILLED = {"block", "classic", "oval", "diamond", "blockThin", "classicThin", "diamondThin"}


def _marker(kind: str, tip: Point, prev: Point, size: float, stroke: Stroke, filled: bool):
    dx, dy = tip[0] - prev[0], tip[1] - prev[1]
    length = math.hypot(dx, dy) or 1
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux
    s = size + stroke.width
    plain = Stroke(stroke.color, stroke.width, None, stroke.opacity)
    fill = stroke.color if filled and kind in _FILLED else None

    def at(back: float, side: float) -> Point:
        return tip[0] - ux * back + nx * side, tip[1] - uy * back + ny * side

    thin = kind.endswith("Thin")
    half = s * (0.33 if thin else 0.5)
    if kind in ("block", "blockThin"):
        return [Poly([tip, at(s * 1.2, half), at(s * 1.2, -half)], True, fill or "#ffffff", plain)]
    if kind in ("classic", "classicThin"):
        return [
            Poly(
                [tip, at(s * 1.2, half), at(s * 0.85, 0), at(s * 1.2, -half)],
                True,
                fill or "#ffffff",
                plain,
            )
        ]
    if kind in ("open", "openThin"):
        return [Poly([at(s * 1.2, half), tip, at(s * 1.2, -half)], False, None, plain)]
    if kind == "oval":
        c = at(s / 2, 0)
        return [Ellipse(c[0], c[1], s / 2, s / 2, fill or "#ffffff", plain)]
    if kind in ("diamond", "diamondThin"):
        return [
            Poly([tip, at(s, half), at(2 * s, 0), at(s, -half)], True, fill or "#ffffff", plain)
        ]
    out = []
    many = kind in ("ERmany", "ERoneToMany", "ERzeroToMany")
    if many:
        out.append(Poly([at(0, s), at(s * 1.4, 0), at(0, -s)], False, None, plain))
    if kind in ("ERone", "ERmandOne", "ERoneToMany", "ERzeroToOne"):
        out.append(Poly([at(s * 1.8, s * 0.8), at(s * 1.8, -s * 0.8)], False, None, plain))
    if kind == "ERmandOne":
        out.append(Poly([at(s * 1.2, s * 0.8), at(s * 1.2, -s * 0.8)], False, None, plain))
    if kind in ("ERzeroToMany", "ERzeroToOne"):
        c = at(s * 2.6, 0)
        out.append(Ellipse(c[0], c[1], s * 0.5, s * 0.5, "#ffffff", plain))
    return out


def connector_primitives(edge: Connector) -> list:
    style = edge.style
    if len(edge.points) < 2:
        return []
    stroke = _stroke(style)
    out: list = [Poly(list(edge.points), False, None, stroke)]
    if stroke.color:
        end = style.get("endArrow", "classic")
        if end and end != "none":
            out += _marker(
                end,
                edge.points[-1],
                edge.points[-2],
                _num(style, "endSize", 6),
                stroke,
                style.get("endFill", "1") != "0",
            )
        start = style.get("startArrow", "none")
        if start and start != "none":
            out += _marker(
                start,
                edge.points[0],
                edge.points[1],
                _num(style, "startSize", 6),
                stroke,
                style.get("startFill", "1") != "0",
            )
    for label in edge.labels:
        out.append(Text(label))
    return out


def primitives(scene: Scene) -> list:
    out: list = []
    for item in scene.items:
        out += shape_primitives(item) if isinstance(item, Shape) else connector_primitives(item)
    return out


def canvas(scene: Scene, border: float = 10, aspect: Optional[float] = None) -> Box:
    """The page area to draw: content bounds plus a border, padded to an aspect ratio."""
    x, y, w, h = scene.bounds()
    x, y, w, h = x - border, y - border, w + 2 * border, h + 2 * border
    if aspect:
        if w / h < aspect:
            extra = h * aspect - w
            x, w = x - extra / 2, w + extra
        else:
            extra = w / aspect - h
            y, h = y - extra / 2, h + extra
    return x, y, max(w, 1), max(h, 1)


# ---------------------------------------------------------------- SVG


def _svg_stroke(stroke: Stroke) -> str:
    if not stroke.color:
        return ' stroke="none"'
    out = f' stroke={quoteattr(stroke.color)} stroke-width="{stroke.width:g}"'
    if stroke.dash:
        out += ' stroke-dasharray="' + " ".join(f"{v:g}" for v in stroke.dash) + '"'
    if stroke.opacity < 1:
        out += f' stroke-opacity="{stroke.opacity:g}"'
    return out + ' stroke-linejoin="round"'


def _svg_fill(fill: Optional[str], opacity: float) -> str:
    if not fill:
        return ' fill="none"'
    out = f" fill={quoteattr(fill)}"
    return out + (f' fill-opacity="{opacity:g}"' if opacity < 1 else "")


def _svg_text(label: Label) -> list[str]:
    out = []
    x, y, w, h = label.box
    if label.background:
        out.append(
            f'<rect x="{x - 2:.2f}" y="{y:.2f}" width="{w + 4:.2f}" height="{h:.2f}"'
            f" fill={quoteattr(label.background)}/>"
        )
    anchor = {"left": "start", "right": "end"}.get(label.align, "middle")
    tx = {"left": x, "right": x + w}.get(label.align, x + w / 2)
    family = f"{label.font_family}, Helvetica, Arial, sans-serif"
    attrs = (
        f' font-family={quoteattr(family)} font-size="{label.font_size:g}"'
        f' fill={quoteattr(label.font_color)} text-anchor="{anchor}"'
    )
    if label.bold:
        attrs += ' font-weight="bold"'
    if label.italic:
        attrs += ' font-style="italic"'
    if label.underline:
        attrs += ' text-decoration="underline"'
    step = label.font_size * LINE_HEIGHT
    lines = []
    for i, line in enumerate(label.lines):
        baseline = y + i * step + label.font_size * (LINE_HEIGHT - 1) / 2 + label.font_size * 0.8
        lines.append(f'<tspan x="{tx:.2f}" y="{baseline:.2f}">{escape(line)}</tspan>')
    out.append(f'<text xml:space="preserve"{attrs}>{"".join(lines)}</text>')
    return out


def _svg_points(points: list[Point]) -> str:
    return " ".join(f"{px:.2f},{py:.2f}" for px, py in points)


def _href(uri: str) -> str:
    """Turn draw.io's `data:mime,base64` form back into a standard data URI."""
    if uri.startswith("data:") and ";base64," not in uri:
        head, _, data = uri.partition(",")
        return f"{head};base64,{data}"
    return uri


def to_svg(
    scene: Scene,
    *,
    border: float = 10,
    aspect: Optional[float] = None,
    background: Optional[str] = None,
) -> str:
    """The page as a standalone SVG document."""
    x, y, w, h = canvas(scene, border, aspect)
    body = []
    fill = scene.background if background is None else background
    if fill and fill != "none":
        body.append(
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}"'
            f" fill={quoteattr(fill)}/>"
        )
    for item in primitives(scene):
        if isinstance(item, Poly):
            tag = "polygon" if item.closed else "polyline"
            fill_attr = _svg_fill(item.fill, item.fill_opacity) if item.closed else ' fill="none"'
            body.append(
                f'<{tag} points="{_svg_points(item.points)}"{fill_attr}{_svg_stroke(item.stroke)}/>'
            )
        elif isinstance(item, Ellipse):
            body.append(
                f'<ellipse cx="{item.cx:.2f}" cy="{item.cy:.2f}" rx="{item.rx:.2f}"'
                f' ry="{item.ry:.2f}"{_svg_fill(item.fill, item.fill_opacity)}'
                f"{_svg_stroke(item.stroke)}/>"
            )
        elif isinstance(item, Picture):
            bx, by, bw, bh = item.box
            body.append(
                f'<image x="{bx:.2f}" y="{by:.2f}" width="{bw:.2f}" height="{bh:.2f}"'
                f' preserveAspectRatio="xMidYMid meet" href={quoteattr(_href(item.uri))}/>'
            )
        else:
            body += _svg_text(item.label)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" width="{w:.0f}" height="{h:.0f}"'
        f' viewBox="{x:.2f} {y:.2f} {w:.2f} {h:.2f}">\n' + "\n".join(body) + "\n</svg>\n"
    )


# ---------------------------------------------------------------- Pillow


def _rgba(color: Optional[str], opacity: float = 1.0):
    from PIL import ImageColor

    if not color:
        return None
    try:
        rgb = ImageColor.getrgb(color)
    except ValueError:
        rgb = (0, 0, 0)
    return (*rgb[:3], int(255 * max(0.0, min(1.0, opacity))))


def _dashes(points: list[Point], dash: tuple[float, ...]):
    """Split a polyline into the drawn pieces of a dash pattern."""
    pieces, current = [], [points[0]]
    pattern, i, left, on = list(dash), 0, dash[0], True
    for a, b in zip(points, points[1:]):
        seg = math.dist(a, b)
        pos = 0.0
        while seg - pos > left:
            pos += left
            t = pos / seg
            p = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            if on:
                current.append(p)
                pieces.append(current)
            current = [p]
            on = not on
            i = (i + 1) % len(pattern)
            left = pattern[i]
        left -= seg - pos
        if on:
            current.append(b)
        else:
            current = [b]
    if on and len(current) > 1:
        pieces.append(current)
    return pieces


def to_image(
    scene: Scene,
    *,
    scale: float = 1,
    border: float = 10,
    aspect: Optional[float] = None,
    background: Optional[str] = None,
    transparent: bool = False,
):
    """The page as a Pillow image. Requires Pillow (`pip install drawio-python[render]`)."""
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise RuntimeError(
            "PNG, JPEG and PDF output needs Pillow: pip install 'drawio-python[render]'."
            " SVG output works without it."
        ) from exc
    from .fonts import font

    x0, y0, w, h = canvas(scene, border, aspect)
    width, height = max(1, round(w * scale)), max(1, round(h * scale))
    ss = 2 if width * height * 4 <= 40_000_000 else 1  # supersample for smooth edges
    k = scale * ss
    fill = scene.background if background is None else background
    base = (0, 0, 0, 0) if transparent or not fill or fill == "none" else _rgba(fill)
    image = Image.new("RGBA", (width * ss, height * ss), base)
    draw = ImageDraw.Draw(image, "RGBA")

    def pt(p: Point):
        return ((p[0] - x0) * k, (p[1] - y0) * k)

    def line(points, stroke: Stroke):
        color = _rgba(stroke.color, stroke.opacity)
        if not color or len(points) < 2:
            return
        lw = max(1, round(stroke.width * k))
        runs = _dashes(points, stroke.dash) if stroke.dash else [points]
        for run in runs:
            draw.line([pt(p) for p in run], fill=color, width=lw, joint="curve")

    for item in primitives(scene):
        if isinstance(item, Poly):
            if item.closed and item.fill:
                draw.polygon([pt(p) for p in item.points], fill=_rgba(item.fill, item.fill_opacity))
            pts = item.points + ([item.points[0]] if item.closed else [])
            line(pts, item.stroke)
        elif isinstance(item, Ellipse):
            box = [
                pt((item.cx - item.rx, item.cy - item.ry)),
                pt((item.cx + item.rx, item.cy + item.ry)),
            ]
            if item.fill:
                draw.ellipse(box, fill=_rgba(item.fill, item.fill_opacity))
            if item.stroke.color:
                if item.stroke.dash:
                    line(_arc(item.cx, item.cy, item.rx, item.ry, 0, 2 * math.pi, 72), item.stroke)
                else:
                    draw.ellipse(
                        box,
                        outline=_rgba(item.stroke.color, item.stroke.opacity),
                        width=max(1, round(item.stroke.width * k)),
                    )
        elif isinstance(item, Picture):
            _paste(image, item, pt, k)
        else:
            _draw_text(draw, item.label, pt, k, font)
    if ss > 1:
        image = image.resize((width, height), Image.LANCZOS)
    return image


def _paste(image, item: Picture, pt, k) -> None:
    from PIL import Image

    uri = _href(item.uri)
    if not uri.startswith("data:") or ";base64," not in uri or "svg" in uri.split(",")[0]:
        return  # remote and SVG pictures are left blank in raster output
    try:
        picture = Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1]))).convert("RGBA")
    except Exception:
        return
    bx, by, bw, bh = item.box
    ratio = min(bw / picture.width, bh / picture.height)
    size = (max(1, round(picture.width * ratio * k)), max(1, round(picture.height * ratio * k)))
    picture = picture.resize(size, Image.LANCZOS)
    left, top = pt((bx + (bw - picture.width / k) / 2, by + (bh - picture.height / k) / 2))
    image.alpha_composite(picture, (round(left), round(top)))


def _draw_text(draw, label: Label, pt, k, font) -> None:
    from .fonts import runs

    x, y, w, h = label.box
    if label.background:
        draw.rectangle([pt((x - 2, y)), pt((x + w + 2, y + h))], fill=_rgba(label.background))
    size = label.font_size * k
    face = font(label.font_family, size, bold=label.bold, italic=label.italic)
    color = _rgba(label.font_color)
    step = label.font_size * LINE_HEIGHT
    for i, text in enumerate(label.lines):
        baseline = y + i * step + label.font_size * (LINE_HEIGHT - 1) / 2 + label.font_size * 0.8
        pieces = runs(face, text, size)
        width = sum(draw.textlength(chunk, font=f) for f, chunk in pieces)
        if label.align == "left":
            left = pt((x, baseline))[0]
        elif label.align == "right":
            left = pt((x + w, baseline))[0] - width
        else:
            left = pt((x + w / 2, baseline))[0] - width / 2
        top = pt((x, baseline))[1]
        cursor = left
        for f, chunk in pieces:
            try:
                draw.text((cursor, top), chunk, font=f, fill=color, anchor="ls")
            except (ValueError, TypeError):  # bitmap fallback fonts do not support anchors
                draw.text((cursor, top - size * 0.8), chunk, font=f, fill=color)
            cursor += draw.textlength(chunk, font=f)
        if label.underline:
            draw.line(
                [(left, top + 2), (left + width, top + 2)], fill=color, width=max(1, round(k))
            )
