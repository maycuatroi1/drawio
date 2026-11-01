"""Editable draw.io XML, with no browser or third-party runtime dependency."""

from __future__ import annotations

import base64
import math
import mimetypes
import os
import re
import secrets
import stat
import xml.etree.ElementTree as ET
import zlib
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Union
from urllib.parse import quote, unquote

from . import text as _metrics
from .shapes import style_for

MAX_XML_BYTES = 10 * 1024 * 1024
_INVALID_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")
_GENERATED_ID = re.compile(r"^[ne][0-9]+$")
_THEME_ARROW = object()


def _text(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("Labels, names and IDs must be strings")
    if _INVALID_XML.search(value):
        raise ValueError("Text contains a character forbidden by XML 1.0")
    return value


def _identifier(value: str) -> str:
    if not _text(value).strip():
        raise ValueError("IDs and page names cannot be empty")
    return value


def _number(value: float, *, positive: bool = False) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("Coordinates and dimensions must be numbers")
    if not math.isfinite(value) or (positive and value <= 0):
        raise ValueError("Coordinates must be finite; dimensions must be positive")
    return str(value)


def _style(defaults: dict, overrides: Optional[Mapping] = None) -> str:
    merged = {**defaults, **(overrides or {})}
    parts = []
    for key, value in merged.items():
        _identifier(key)
        value = str(int(value)) if isinstance(value, bool) else str(value)
        _text(value)
        if any(c in key for c in ";=") or ";" in value:
            raise ValueError("Style keys/values cannot contain style delimiters")
        parts.append(f"{key}={value};")
    return "".join(parts)


def _parse(xml: str) -> ET.Element:
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", xml, re.IGNORECASE):
        raise ValueError("DTD and entity declarations are not supported")
    try:
        return ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid draw.io XML: {exc}") from exc


def _inflate(text: str, limit: int) -> str:
    try:
        raw = base64.b64decode("".join(text.split()), validate=True)
        decoder = zlib.decompressobj(wbits=-15)
        data = decoder.decompress(raw, limit + 1)
        if len(data) > limit or decoder.unconsumed_tail:
            raise ValueError("Expanded diagram exceeds the XML size limit")
        if not decoder.eof or decoder.unused_data:
            raise ValueError("Incomplete or trailing compressed diagram data")
        return unquote(data.decode("utf-8"), errors="strict")
    except (zlib.error, UnicodeError, base64.binascii.Error) as exc:
        raise ValueError("Invalid compressed draw.io diagram") from exc


def parse_style(style: Optional[str]) -> dict:
    """Split a draw.io style string into a dict; bare names such as `ellipse` map to None."""
    result: dict = {}
    for part in (style or "").split(";"):
        part = part.strip()
        if not part:
            continue
        key, sep, value = part.partition("=")
        result[key] = value if sep else None
    return result


def _padding(style: Mapping) -> tuple[float, float]:
    """Horizontal and vertical room draw.io keeps between a shape's edge and its label."""
    spacing = float(style.get("spacing", "2") or 0)

    def get(key: str) -> float:
        return float(style.get(key, "0") or 0)

    pad_x = 2 * spacing + get("spacingLeft") + get("spacingRight")
    pad_y = 2 * spacing + get("spacingTop") + get("spacingBottom")
    return pad_x, pad_y


def _title_offset(style: Mapping, size: float) -> float:
    """Room taken by a container's title, which sits at the top of the box."""
    if style.get("container") == "1" and style.get("verticalAlign") == "top":
        return size * _metrics.LINE_HEIGHT
    return 0.0


def _image_uri(source: Union[str, Path]) -> str:
    """A draw.io image reference: URL, or a data URI in draw.io's `data:mime,base64` form."""
    if isinstance(source, str) and source.startswith(("http://", "https://")):
        return _text(source)
    if isinstance(source, str) and source.startswith("data:"):
        head, sep, data = source.partition(",")
        if not sep:
            raise ValueError("A data URI needs a comma before its data")
        mime = head[5:].split(";")[0]
        if ";base64" not in head:
            data = base64.b64encode(unquote(data).encode("utf-8")).decode("ascii")
        return f"data:{mime},{data}"
    path = Path(source).expanduser()
    mime = mimetypes.guess_type(path.name)[0]
    if path.suffix.lower() == ".svg":
        mime = "image/svg+xml"
    if not mime or not mime.startswith("image/"):
        raise ValueError(f"Not an image file: {path}")
    return f"data:{mime},{base64.b64encode(path.read_bytes()).decode('ascii')}"


@dataclass(frozen=True)
class Theme:
    """Default styles for newly created shapes and connectors."""

    font_family: str = "Helvetica"
    font_size: int = 18
    fill_color: str = "#ffffff"
    stroke_color: str = "#8091a5"
    text_color: str = "#182b40"
    line_color: str = "#6b7d91"
    stroke_width: float = 1.5
    edge_width: float = 2
    end_arrow: str = "block"
    spacing: float = 10

    @classmethod
    def drawio(cls, **overrides) -> Theme:
        """The look of a fresh shape in the draw.io editor: Helvetica 12, black lines."""
        values = dict(
            font_size=12,
            fill_color="#ffffff",
            stroke_color="#000000",
            text_color="#000000",
            line_color="#000000",
            stroke_width=1,
            edge_width=1,
            end_arrow="classic",
            spacing=2,
        )
        return cls(**{**values, **overrides})


@dataclass(eq=False, frozen=True)
class Cell:
    """A shape or connector belonging to one page. Coordinates stay in XML."""

    id: str
    page: Page
    element: ET.Element

    @property
    def label(self) -> str:
        return self.element.get("value", "")

    @property
    def text(self) -> str:
        """The visible label, with HTML markup removed when the cell uses html=1."""
        return _metrics.plain(self.label, html_label=self.style.get("html") == "1")

    @property
    def style(self) -> dict:
        return parse_style(self.element.get("style"))

    @property
    def is_vertex(self) -> bool:
        return self.element.get("vertex") == "1"

    @property
    def is_edge(self) -> bool:
        return self.element.get("edge") == "1"

    @property
    def parent_id(self) -> Optional[str]:
        return self.element.get("parent")

    @property
    def source_id(self) -> Optional[str]:
        return self.element.get("source")

    @property
    def target_id(self) -> Optional[str]:
        return self.element.get("target")

    def _geometry(self, attr: str) -> float:
        geometry = self.element.find("mxGeometry")
        return 0.0 if geometry is None else float(geometry.get(attr, "0"))

    @property
    def x(self) -> float:
        """Left edge, relative to the parent container."""
        return self._geometry("x")

    @property
    def y(self) -> float:
        """Top edge, relative to the parent container."""
        return self._geometry("y")

    @property
    def width(self) -> float:
        return self._geometry("width")

    @property
    def height(self) -> float:
        return self._geometry("height")

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """(x, y, width, height) in page coordinates."""
        return self.page.bounds(self)

    def set_label(self, label: str) -> Cell:
        self.element.set("value", _text(label))
        return self

    def set_style(self, style: Optional[Mapping] = None, **properties) -> Cell:
        """Merge style properties into the cell; a value of None removes the property."""
        merged = self.style
        for key, value in {**(style or {}), **properties}.items():
            if value is None:
                merged.pop(key, None)
            else:
                merged[key] = value
        current = {k: v for k, v in merged.items() if v is not None}
        bare = {k: None for k, v in merged.items() if v is None}
        self.element.set("style", "".join(f"{k};" for k in bare) + _style({}, current))
        return self

    def move(self, x: float, y: float, *, absolute: bool = False) -> Cell:
        """Move a shape; with absolute=True, x and y are page coordinates."""
        if absolute:
            ox, oy = self.page._parent_origin(self.element.get("parent"))
            x, y = x - ox, y - oy
        geometry = self.page._vertex_geometry(self)
        geometry.set("x", _number(x))
        geometry.set("y", _number(y))
        return self

    def resize(self, width: float, height: float) -> Cell:
        geometry = self.page._vertex_geometry(self)
        geometry.set("width", _number(width, positive=True))
        geometry.set("height", _number(height, positive=True))
        return self


class Page:
    """One draw.io tab; child geometry is relative to its parent container."""

    def __init__(self, diagram: ET.Element, theme: Theme):
        self.element = diagram
        self.theme = theme
        model = diagram.find("mxGraphModel")
        if model is None or model.find("root") is None:
            raise ValueError("A page must contain mxGraphModel/root")
        self.model = model
        self.root = model.find("root")

    @property
    def id(self) -> str:
        return self.element.get("id", "")

    @property
    def name(self) -> str:
        return self.element.get("name", "")

    @name.setter
    def name(self, value: str) -> None:
        self.element.set("name", _identifier(value))

    def _index(self) -> dict[str, ET.Element]:
        result = {}
        for entry in self.root:
            # draw.io may wrap mxCell in an object/UserObject with metadata.
            cell = entry if entry.tag == "mxCell" else entry.find("mxCell")
            if cell is None:
                continue
            id = entry.get("id") or cell.get("id")
            if id is None:
                raise ValueError("A cell is missing its ID")
            _identifier(id)
            if id in result:
                raise ValueError(f"Duplicate cell ID: {id}")
            result[id] = cell
        return result

    @property
    def cells(self) -> tuple[Cell, ...]:
        return tuple(Cell(id, self, el) for id, el in self._index().items())

    def get(self, id: str) -> Cell:
        try:
            return Cell(id, self, self._index()[id])
        except KeyError as exc:
            raise ValueError(f"Unknown cell ID: {id}") from exc

    def _resolve(self, ref: Union[Cell, str], *, vertex: bool = True) -> str:
        id = ref.id if isinstance(ref, Cell) else _identifier(ref)
        cell = self.get(id)
        if isinstance(ref, Cell) and (ref.page is not self or ref.element is not cell.element):
            raise ValueError("A cell reference belongs to another page")
        if vertex and cell.element.get("vertex") != "1":
            raise ValueError(f"Expected a shape, not a layer or connector: {id}")
        return id

    def _new_id(self, id: Optional[str], prefix: str) -> str:
        existing = self._index()
        if id is not None:
            id = _identifier(id)
            if id in existing:
                hint = ""
                if _GENERATED_ID.match(id):
                    hint = (
                        f" ({id} has the form of the IDs generated for cells created without"
                        " an id: n1, n2... for shapes, e1, e2... for connectors. Pass an id"
                        " to every cell, or use another naming scheme.)"
                    )
                raise ValueError(f"Duplicate cell ID: {id}{hint}")
            return id
        i = 1
        while f"{prefix}{i}" in existing:
            i += 1
        return f"{prefix}{i}"

    def box(
        self,
        label: str,
        x: float,
        y: float,
        width: float = 200,
        height: float = 90,
        *,
        id: Optional[str] = None,
        parent: Optional[Union[Cell, str]] = None,
        style: Optional[Mapping] = None,
        html: bool = False,
        shape: Optional[str] = None,
        absolute: bool = False,
        autosize: bool = False,
    ) -> Cell:
        """Add a shape. Labels are plain text unless html=True is explicit.

        `shape` names a built-in draw.io shape (see drawio.shapes.SHAPES, e.g. "ellipse",
        "cylinder", "rhombus") or any raw draw.io shape name. With absolute=True, x and y
        are page coordinates even inside a container. With autosize=True the box grows to
        fit its label.
        """
        id = self._new_id(id, "n")
        parent_id = "1" if parent is None else self._resolve(parent)
        if absolute:
            ox, oy = self._parent_origin(parent_id)
            x, y = x - ox, y - oy
        geometry = dict(
            x=_number(x),
            y=_number(y),
            width=_number(width, positive=True),
            height=_number(height, positive=True),
        )
        defaults = {
            "rounded": 0,
            "whiteSpace": "wrap",
            "fontFamily": self.theme.font_family,
            "fontSize": self.theme.font_size,
            "fontColor": self.theme.text_color,
            "fillColor": self.theme.fill_color,
            "strokeColor": self.theme.stroke_color,
            "strokeWidth": self.theme.stroke_width,
            "spacing": self.theme.spacing,
            **style_for(shape),
        }
        # Do not let a style mapping silently turn plain text into trusted HTML.
        styles = _style(defaults, {**(style or {}), "html": html})
        element = ET.SubElement(
            self.root,
            "mxCell",
            id=id,
            value=_text(label),
            style=styles,
            vertex="1",
            parent=parent_id,
        )
        ET.SubElement(element, "mxGeometry", **geometry, **{"as": "geometry"})
        cell = Cell(id, self, element)
        if autosize:
            self.autosize(cell)
        return cell

    def ellipse(
        self, label: str, x: float, y: float, width: float = 120, height: float = 80, **kwargs
    ) -> Cell:
        """Add an ellipse; keyword arguments are those of box()."""
        return self.box(label, x, y, width, height, shape="ellipse", **kwargs)

    def image(
        self,
        source: Union[str, Path],
        x: float,
        y: float,
        width: float = 64,
        height: float = 64,
        *,
        label: str = "",
        style: Optional[Mapping] = None,
        **kwargs,
    ) -> Cell:
        """Add a picture from a local file (embedded in the diagram), a URL or a data URI.

        The label, if any, sits under the picture.
        """
        uri = _image_uri(source)
        styles = {
            "shape": "image",
            "image": uri,
            "imageAspect": 1,
            "aspect": "fixed",
            "verticalLabelPosition": "bottom",
            "verticalAlign": "top",
            "fillColor": "none",
            "strokeColor": "none",
            **(style or {}),
        }
        return self.box(label, x, y, width, height, style=styles, **kwargs)

    def container(
        self,
        label: str,
        x: float,
        y: float,
        width: float,
        height: float,
        *,
        style: Optional[Mapping] = None,
        **kwargs,
    ) -> Cell:
        """Add a parent block; its children remain independently editable."""
        styles = {
            "verticalAlign": "top",
            "spacingTop": 16,
            "container": 1,
            "collapsible": 0,
            "recursiveResize": 0,
            "fontStyle": 1,
            **(style or {}),
        }
        return self.box(label, x, y, width, height, style=styles, **kwargs)

    def text(
        self,
        label: str,
        x: float,
        y: float,
        width: float = 400,
        height: float = 40,
        *,
        style: Optional[Mapping] = None,
        **kwargs,
    ) -> Cell:
        return self.box(
            label,
            x,
            y,
            width,
            height,
            style={
                "fillColor": "none",
                "strokeColor": "none",
                "align": "left",
                "spacing": 0,
                **(style or {}),
            },
            **kwargs,
        )

    def connect(
        self,
        source: Union[Cell, str],
        target: Union[Cell, str],
        label: str = "",
        *,
        id: Optional[str] = None,
        source_port=None,
        target_port=None,
        waypoints=(),
        dashed: bool = False,
        style: Optional[Mapping] = None,
        arrow=_THEME_ARROW,
        start_arrow: Optional[str] = None,
    ) -> Cell:
        """Add an orthogonal connector; waypoints use page coordinates.

        `arrow` and `start_arrow` name the end markers (see drawio.shapes.ARROWS); None
        draws a plain line end, so arrow=None gives an undirected connector.
        """
        source_id, target_id = self._resolve(source), self._resolve(target)
        id = self._new_id(id, "e")
        end = self.theme.end_arrow if arrow is _THEME_ARROW else (arrow or "none")
        defaults = {
            "edgeStyle": "orthogonalEdgeStyle",
            "rounded": 0,
            "html": 0,
            "endArrow": end,
            "endFill": 1,
            "startArrow": start_arrow or "none",
            "startFill": 1,
            "strokeWidth": self.theme.edge_width,
            "fontFamily": self.theme.font_family,
            "fontSize": self.theme.font_size,
            "fontColor": self.theme.text_color,
            "strokeColor": self.theme.line_color,
            "labelBackgroundColor": "#ffffff",
            "dashed": dashed,
        }
        for prefix, port in (("exit", source_port), ("entry", target_port)):
            if port is not None:
                if len(port) != 2:
                    raise ValueError("A port is an (x, y) pair in [0, 1]")
                for axis, value in zip(("X", "Y"), port):
                    _number(value)
                    if not 0 <= value <= 1:
                        raise ValueError("Port coordinates must lie in [0, 1]")
                    defaults[prefix + axis] = value
        points = []
        for point in waypoints:
            if len(point) != 2:
                raise ValueError("A waypoint is an (x, y) pair")
            points.append((_number(point[0]), _number(point[1])))
        styles = _style(defaults, {**(style or {}), "html": 0})
        element = ET.SubElement(
            self.root,
            "mxCell",
            id=id,
            value=_text(label),
            style=styles,
            edge="1",
            parent="1",
            source=source_id,
            target=target_id,
        )
        geometry = ET.SubElement(element, "mxGeometry", relative="1", **{"as": "geometry"})
        if points:
            array = ET.SubElement(geometry, "Array", **{"as": "points"})
            for x, y in points:
                ET.SubElement(array, "mxPoint", x=x, y=y)
        return Cell(id, self, element)

    def _entries(self) -> dict[str, ET.Element]:
        """Map each cell ID to its element directly under <root> (mxCell or object)."""
        result = {}
        for entry in self.root:
            inner = entry.find("mxCell")
            id = entry.get("id") or (inner.get("id") if inner is not None else None)
            if id is not None:
                result[id] = entry
        return result

    def _vertex_geometry(self, cell: Cell) -> ET.Element:
        if not cell.is_vertex:
            raise ValueError(f"Expected a shape, not a layer or connector: {cell.id}")
        geometry = cell.element.find("mxGeometry")
        if geometry is None:
            geometry = ET.SubElement(cell.element, "mxGeometry", **{"as": "geometry"})
        return geometry

    def _parent_origin(self, parent_id: Optional[str]) -> tuple[float, float]:
        """Page coordinates of the origin that children of `parent_id` are placed from."""
        index = self._index()
        x = y = 0.0
        seen = set()
        while parent_id in index and parent_id not in seen:
            seen.add(parent_id)
            cell = index[parent_id]
            if cell.get("vertex") != "1":
                break
            geometry = cell.find("mxGeometry")
            if geometry is not None and geometry.get("relative") != "1":
                x += float(geometry.get("x", "0"))
                y += float(geometry.get("y", "0"))
            parent_id = cell.get("parent")
        return x, y

    def bounds(self, ref: Union[Cell, str]) -> tuple[float, float, float, float]:
        """(x, y, width, height) of a shape in page coordinates."""
        cell = self.get(self._resolve(ref))
        ox, oy = self._parent_origin(cell.parent_id)
        return ox + cell.x, oy + cell.y, cell.width, cell.height

    @property
    def shapes(self) -> tuple[Cell, ...]:
        return tuple(c for c in self.cells if c.is_vertex)

    @property
    def edges(self) -> tuple[Cell, ...]:
        return tuple(c for c in self.cells if c.is_edge)

    def children(self, ref: Union[Cell, str, None] = None) -> tuple[Cell, ...]:
        """Shapes whose parent is `ref`, or top-level shapes when ref is None."""
        parent_id = "1" if ref is None else self._resolve(ref)
        return tuple(c for c in self.shapes if c.parent_id == parent_id)

    def find(self, label: str) -> tuple[Cell, ...]:
        """Cells whose visible label equals `label`."""
        return tuple(c for c in self.cells if c.text == label)

    def remove(self, ref: Union[Cell, str]) -> None:
        """Delete a cell with its children and every connector attached to them."""
        id = ref.id if isinstance(ref, Cell) else _identifier(ref)
        if id in ("0", "1"):
            raise ValueError("The root cell and default layer cannot be removed")
        index = self._index()
        if id not in index:
            raise ValueError(f"Unknown cell ID: {id}")
        doomed = {id}
        changed = True
        while changed:
            changed = False
            for other, cell in index.items():
                if other in doomed:
                    continue
                refs = (cell.get("parent"), cell.get("source"), cell.get("target"))
                if any(r in doomed for r in refs):
                    doomed.add(other)
                    changed = True
        for other, entry in self._entries().items():
            if other in doomed:
                self.root.remove(entry)

    def autosize(self, ref: Union[Cell, str], *, max_width: Optional[float] = None) -> Cell:
        """Grow a shape so its label fits: taller first, wider up to max_width if a word
        cannot wrap. Sizes come from drawio.text, an estimate of draw.io's text layout."""
        cell = self.get(self._resolve(ref))
        style = cell.style
        text = cell.text
        if not text.strip():
            return cell
        size = float(style.get("fontSize", self.theme.font_size))
        bold = int(float(style.get("fontStyle", "0"))) & 1 == 1
        family = style.get("fontFamily", self.theme.font_family)
        pad_x, pad_y = _padding(style)
        width = cell.width
        word = _metrics.longest_word(text, size, bold=bold, family=family)
        if word + pad_x > width:
            limit = max(width, max_width) if max_width else width
            width = min(limit, math.ceil(word + pad_x + 1))
        wrap = style.get("whiteSpace") == "wrap"
        text_w, text_h, _ = _metrics.measure(
            text, size, width=width - pad_x if wrap else None, bold=bold, family=family
        )
        if not wrap and text_w + pad_x > width:
            width = math.ceil(text_w + pad_x + 1)
        if style.get("verticalLabelPosition") in ("bottom", "top"):
            height = cell.height  # the label sits outside the shape
        else:
            height = max(cell.height, math.ceil(text_h + pad_y + _title_offset(style, size)))
        return cell.resize(width, height)

    def fit(self, ref: Union[Cell, str, None] = None, *, padding: float = 20) -> None:
        """Grow containers to enclose their children, plus `padding` on the right and below.

        With no argument, fits every container (innermost first) and enlarges the page so
        that all shapes lie on it.
        """
        if ref is not None:
            self._fit_one(self.get(self._resolve(ref)), padding)
            return
        index = self._index()

        def depth(cell: Cell) -> int:
            n, parent = 0, cell.parent_id
            while parent in index and parent not in ("0", "1"):
                n, parent = n + 1, index[parent].get("parent")
            return n

        parents = {c.parent_id for c in self.shapes}
        for cell in sorted((c for c in self.shapes if c.id in parents), key=depth, reverse=True):
            self._fit_one(cell, padding)
        right = bottom = 0.0
        for cell in self.shapes:
            x, y, w, h = self.bounds(cell)
            right, bottom = max(right, x + w), max(bottom, y + h)
        width = max(float(self.model.get("pageWidth", "0")), math.ceil(right + padding))
        height = max(float(self.model.get("pageHeight", "0")), math.ceil(bottom + padding))
        for attr, value in (("pageWidth", width), ("pageHeight", height)):
            self.model.set(attr, _number(value))

    def _fit_one(self, cell: Cell, padding: float) -> None:
        children = self.children(cell)
        if not children:
            return
        right = max(c.x + c.width for c in children) + padding
        bottom = max(c.y + c.height for c in children) + padding
        cell.resize(max(cell.width, right), max(cell.height, bottom))

    def validate(self, *, check_bounds: bool = False) -> None:
        """Check IDs, references and parent cycles; optionally check child bounds."""
        _identifier(self.id)
        _identifier(self.name)
        index = self._index()
        if "0" not in index or "1" not in index:
            raise ValueError("A page requires root cell 0 and default layer 1")
        if index["0"].get("parent") is not None or index["1"].get("parent") != "0":
            raise ValueError("Invalid root/default layer hierarchy")
        for id, cell in index.items():
            parent = cell.get("parent")
            if id != "0" and parent is None:
                raise ValueError(f"Cell {id} is missing a parent")
            for attr in ("parent", "source", "target"):
                ref = cell.get(attr)
                if ref is not None and ref not in index:
                    raise ValueError(f"Cell {id} has an unknown {attr}: {ref}")
                if attr != "parent" and ref is not None and index[ref].get("vertex") != "1":
                    raise ValueError(f"Connector {id} references a non-shape: {ref}")
            seen = {id}
            while parent is not None:
                if parent not in index:
                    raise ValueError(f"Cell {id} has an unknown ancestor: {parent}")
                if parent in seen:
                    raise ValueError(f"Parent cycle at cell {id}")
                seen.add(parent)
                parent = index[parent].get("parent")
            geometry = cell.find("mxGeometry")
            if cell.get("edge") == "1":
                for endpoint in ("source", "target"):
                    point = (
                        None
                        if geometry is None
                        else geometry.find(f"mxPoint[@as='{endpoint}Point']")
                    )
                    if cell.get(endpoint) is None and point is None:
                        raise ValueError(f"Connector {id} is missing its {endpoint} endpoint")
            if geometry is not None:
                for attr in ("x", "y", "width", "height"):
                    if attr in geometry.attrib:
                        try:
                            number = float(geometry.get(attr))
                        except ValueError as exc:
                            raise ValueError(f"Invalid geometry on {id}") from exc
                        if not math.isfinite(number) or (
                            attr in ("width", "height") and number < 0
                        ):
                            raise ValueError(f"Invalid geometry on {id}")
            if check_bounds and cell.get("vertex") == "1" and cell.get("parent") not in ("0", "1"):
                parent_geometry = index[cell.get("parent")].find("mxGeometry")
                if geometry is None or parent_geometry is None or geometry.get("relative") == "1":
                    continue
                for axis, dimension in (("x", "width"), ("y", "height")):
                    start = float(geometry.get(axis, "0"))
                    end = start + float(geometry.get(dimension, "0"))
                    if start < 0 or end > float(parent_geometry.get(dimension, "0")):
                        raise ValueError(f"Child {id} extends outside its parent")

    def to_xml(self) -> str:
        """Return mxGraphModel XML for Extras > Edit Diagram in draw.io."""
        self.validate()
        return ET.tostring(self.model, encoding="unicode")


class Document:
    """A multi-page .drawio file. Existing page XML and metadata are retained."""

    def __init__(self, *, theme: Optional[Theme] = None):
        self.theme = theme or Theme()
        self.element = ET.Element("mxfile", host="app.diagrams.net", type="device")
        self._pages: list[Page] = []

    @property
    def pages(self) -> tuple[Page, ...]:
        return tuple(self._pages)

    def add_page(
        self,
        name: str,
        *,
        id: Optional[str] = None,
        width: float = 1600,
        height: float = 1000,
        background: str = "#ffffff",
    ) -> Page:
        _identifier(name)
        ids = {p.id for p in self.pages}
        if id is None:
            i = 1
            while f"page-{i}" in ids:
                i += 1
            id = f"page-{i}"
        _identifier(id)
        if id in ids:
            raise ValueError(f"Duplicate page ID: {id}")
        width, height = _number(width, positive=True), _number(height, positive=True)
        background = _text(background)
        diagram = ET.SubElement(self.element, "diagram", id=id, name=name)
        model = ET.SubElement(
            diagram,
            "mxGraphModel",
            dx=width,
            dy=height,
            grid="0",
            gridSize="10",
            guides="1",
            tooltips="1",
            connect="1",
            arrows="1",
            fold="1",
            page="0",
            pageScale="1",
            pageWidth=width,
            pageHeight=height,
            math="0",
            shadow="0",
            background=background,
        )
        root = ET.SubElement(model, "root")
        ET.SubElement(root, "mxCell", id="0")
        ET.SubElement(root, "mxCell", id="1", parent="0")
        page = Page(diagram, self.theme)
        self._pages.append(page)
        return page

    def remove_page(self, ref: Union[Page, str]) -> None:
        """Delete a page, given the Page or its ID."""
        page = ref if isinstance(ref, Page) else self.get_page(ref)
        if page not in self._pages:
            raise ValueError("The page belongs to another document")
        self.element.remove(page.element)
        self._pages.remove(page)

    def import_page(
        self, page: Page, *, id: Optional[str] = None, name: Optional[str] = None
    ) -> Page:
        """Copy a page, usually from another Document, to the end of this one.

        The copy keeps its cell IDs. It keeps its page ID unless that ID is taken here or
        `id` is given.
        """
        ids = {p.id for p in self.pages}
        element = deepcopy(page.element)
        if id is not None:
            _identifier(id)
            if id in ids:
                raise ValueError(f"Duplicate page ID: {id}")
        elif page.id in ids:
            i = 1
            while f"page-{i}" in ids:
                i += 1
            id = f"page-{i}"
        if id is not None:
            element.set("id", id)
        if name is not None:
            element.set("name", _identifier(name))
        self.element.append(element)
        copy = Page(element, self.theme)
        self._pages.append(copy)
        return copy

    def get_page(self, id: str) -> Page:
        for page in self.pages:
            if page.id == id:
                return page
        raise ValueError(f"Unknown page ID: {id}")

    def validate(self, *, check_bounds: bool = False) -> None:
        if not self.pages:
            raise ValueError("A document must contain at least one page")
        if len({p.id for p in self.pages}) != len(self.pages):
            raise ValueError("Duplicate page ID")
        for page in self.pages:
            page.validate(check_bounds=check_bounds)

    def to_xml(self, *, pretty: bool = True) -> str:
        self.validate()
        element = deepcopy(self.element)
        if pretty:
            ET.indent(element, space="  ")
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(element, encoding="unicode")

    def save(self, path, *, overwrite: bool = False) -> Path:
        """Atomically save; refuse to replace a file unless overwrite=True.

        A new file gets the usual permissions for the process umask; a replaced file keeps
        its own.
        """
        path = Path(path).expanduser()
        xml = self.to_xml()
        temporary = path.parent / f".{path.name}.{secrets.token_hex(6)}.tmp"
        try:
            # os.open applies the umask, unlike tempfile, which always creates mode 0600.
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(xml)
            if overwrite:
                try:
                    os.chmod(temporary, stat.S_IMODE(path.stat().st_mode))
                except FileNotFoundError:
                    pass
                os.replace(temporary, path)
            else:
                os.link(temporary, path)  # Exclusive creation; no exists/check race.
        finally:
            temporary.unlink(missing_ok=True)
        return path

    def to_url(self) -> str:
        """Encode the complete document in a draw.io editor URL; no network I/O."""
        data = quote(self.to_xml(pretty=False), safe="~()*!.'-").encode("utf-8")
        compressor = zlib.compressobj(wbits=-15)
        compressed = compressor.compress(data) + compressor.flush()
        return "https://app.diagrams.net/?splash=0#R" + base64.b64encode(compressed).decode("ascii")

    @classmethod
    def load(cls, path, *, max_bytes: int = MAX_XML_BYTES) -> Document:
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
            raise ValueError("max_bytes must be a positive integer")
        with Path(path).expanduser().open("rb") as stream:
            data = stream.read(max_bytes + 1)
        return cls.from_xml(data, max_bytes=max_bytes)

    @classmethod
    def from_xml(cls, xml: Union[str, bytes], *, max_bytes: int = MAX_XML_BYTES) -> Document:
        """Read UTF-8 mxfile, diagram or mxGraphModel XML, including compressed pages."""
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
            raise ValueError("max_bytes must be a positive integer")
        if isinstance(xml, bytes):
            if len(xml) > max_bytes:
                raise ValueError("XML exceeds the size limit")
            xml = xml.decode("utf-8-sig")
        if len(xml.encode("utf-8")) > max_bytes:
            raise ValueError("XML exceeds the size limit")
        element = _parse(xml)
        document = cls()
        if element.tag == "mxGraphModel":
            page = document.add_page("Page 1")
            page.element.remove(page.model)
            page.element.append(element)
            document._pages = [Page(page.element, document.theme)]
        else:
            if element.tag == "diagram":
                document.element.append(element)
            elif element.tag == "mxfile":
                document.element = element
            else:
                raise ValueError("Expected mxfile, diagram or mxGraphModel")
            remaining = max_bytes
            for diagram in document.element.findall("diagram"):
                model = diagram.find("mxGraphModel")
                if model is None:
                    encoded = (diagram.text or "").strip()
                    if not encoded:
                        raise ValueError("Empty diagram without mxGraphModel")
                    decoded = encoded if encoded.startswith("<") else _inflate(encoded, remaining)
                    model = _parse(decoded)
                    if model.tag != "mxGraphModel":
                        raise ValueError("A diagram must contain mxGraphModel")
                    diagram.text = None
                    diagram.append(model)
                remaining -= len(ET.tostring(model, encoding="utf-8"))
                if remaining < 0:
                    raise ValueError("Expanded diagrams exceed the XML size limit")
                document._pages.append(Page(diagram, document.theme))
        document.validate()
        return document
