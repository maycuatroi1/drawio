"""Editable draw.io XML, with no browser or third-party runtime dependency."""

from __future__ import annotations

import base64
import math
import os
import re
import tempfile
import xml.etree.ElementTree as ET
import zlib
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Union
from urllib.parse import quote, unquote

MAX_XML_BYTES = 10 * 1024 * 1024
_INVALID_XML = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")


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


@dataclass(frozen=True)
class Theme:
    """Default styles for newly created shapes and connectors."""

    font_family: str = "Helvetica"
    font_size: int = 18
    fill_color: str = "#ffffff"
    stroke_color: str = "#8091a5"
    text_color: str = "#182b40"
    line_color: str = "#6b7d91"


@dataclass(eq=False, frozen=True)
class Cell:
    """A shape or connector belonging to one page. Coordinates stay in XML."""

    id: str
    page: Page
    element: ET.Element


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
                raise ValueError(f"Duplicate cell ID: {id}")
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
    ) -> Cell:
        """Add a shape. Labels are plain text unless html=True is explicit."""
        id = self._new_id(id, "n")
        parent_id = "1" if parent is None else self._resolve(parent)
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
            "strokeWidth": 1.5,
            "spacing": 10,
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
        return Cell(id, self, element)

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
    ) -> Cell:
        """Add an orthogonal connector; waypoints use page coordinates."""
        source_id, target_id = self._resolve(source), self._resolve(target)
        id = self._new_id(id, "e")
        defaults = {
            "edgeStyle": "orthogonalEdgeStyle",
            "rounded": 0,
            "html": 0,
            "endArrow": "block",
            "endFill": 1,
            "strokeWidth": 2,
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
        """Atomically save; refuse to replace a file unless overwrite=True."""
        path = Path(path).expanduser()
        xml = self.to_xml()
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent, delete=False
            ) as stream:
                temporary = Path(stream.name)
                stream.write(xml)
            if overwrite:
                os.replace(temporary, path)
            else:
                os.link(temporary, path)  # Exclusive creation; no exists/check race.
        finally:
            if temporary is not None:
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
