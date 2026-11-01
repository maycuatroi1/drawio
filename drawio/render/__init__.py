"""Turn a .drawio file into PNG, SVG, PDF or JPEG on any operating system.

Backends, chosen with `backend=`:

- ``native``: built in. SVG with the standard library only; PNG, JPEG and PDF with
  Pillow (``pip install 'drawio-python[render]'``). Draws the shapes this library
  creates and the common draw.io shapes; other stencils become rectangles.
- ``desktop``: the draw.io desktop app's exporter, when installed. Exact.
- ``browser``: the official diagrams.net viewer in headless Chromium through Playwright
  (``pip install 'drawio-python[browser-render]'``). Exact, no desktop app needed.
- ``auto`` (default): desktop if installed, otherwise native.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

from ..document import Document, Page
from ..scene import build

FORMATS = ("png", "svg", "pdf", "jpg")
BACKENDS = ("auto", "native", "desktop", "browser")


@dataclass
class Result:
    path: Path
    backend: str
    page: str
    notes: list[str] = field(default_factory=list)


def _format(output: Path, fmt: Optional[str]) -> str:
    fmt = (fmt or output.suffix.lstrip(".") or "png").lower()
    fmt = "jpg" if fmt == "jpeg" else fmt
    if fmt not in FORMATS:
        raise ValueError(f"Unsupported format {fmt!r}; choose one of {', '.join(FORMATS)}")
    return fmt


def _select(document: Document, page: Union[int, str, None]) -> tuple[int, Page]:
    pages = document.pages
    if not pages:
        raise ValueError("The document has no pages")
    if page is None:
        return 0, pages[0]
    if isinstance(page, int) or (isinstance(page, str) and page.isdigit()):
        index = int(page)
        if not 0 <= index < len(pages):
            raise ValueError(f"Page index {index} is out of range (0..{len(pages) - 1})")
        return index, pages[index]
    for i, p in enumerate(pages):
        if page in (p.id, p.name):
            return i, p
    raise ValueError(f"No page with ID or name {page!r}")


def parse_aspect(value: Union[str, float, None]) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    for sep in (":", "x", "/"):
        if sep in value:
            a, b = value.split(sep, 1)
            return float(a) / float(b)
    return float(value)


def _vector_pdf(svg: str, output: Path) -> bool:
    """Convert SVG to a vector PDF with whatever converter is present."""
    try:
        import cairosvg  # type: ignore

        cairosvg.svg2pdf(bytestring=svg.encode("utf-8"), write_to=str(output))
        return True
    except Exception:
        pass
    converter = shutil.which("rsvg-convert")
    if converter:
        result = subprocess.run(
            [converter, "-f", "pdf", "-o", str(output)],
            input=svg.encode("utf-8"),
            capture_output=True,
            timeout=120,
        )
        return result.returncode == 0 and output.exists()
    return False


def render(
    source: Union[Document, str, Path],
    output: Union[str, Path],
    *,
    page: Union[int, str, None] = None,
    fmt: Optional[str] = None,
    scale: float = 1,
    border: int = 10,
    backend: str = "auto",
    aspect: Union[str, float, None] = None,
    transparent: bool = False,
    background: Optional[str] = None,
    download: bool = True,
) -> Result:
    """Render one page of a document (or of a .drawio file) to an image or PDF.

    `page` is a 0-based index, a page ID or a page name. `aspect` (e.g. "16:9") pads the
    canvas to that ratio so slide tools that fill a picture box do not crop it (native
    backend). Returns which backend drew the file and any notes about the output.
    """
    if backend not in BACKENDS:
        raise ValueError(f"Unknown backend {backend!r}; choose one of {', '.join(BACKENDS)}")
    if scale <= 0:
        raise ValueError("scale must be positive")
    document = source if isinstance(source, Document) else Document.load(source)
    output = Path(output).expanduser()
    fmt = _format(output, fmt)
    index, chosen = _select(document, page)
    ratio = parse_aspect(aspect)
    output.parent.mkdir(parents=True, exist_ok=True)
    notes: list[str] = []

    if backend == "auto":
        from . import desktop

        backend = "desktop" if desktop.find() else "native"
    if backend == "desktop":
        from . import desktop

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.drawio"
            path.write_text(document.to_xml(), encoding="utf-8")
            desktop.export(
                path,
                output,
                fmt=fmt,
                page=index,
                scale=scale,
                border=border,
                transparent=transparent,
            )
        if ratio:
            notes.append("aspect padding applies to the native backend only")
        return Result(output, "desktop", chosen.id, notes)
    if backend == "browser":
        from . import browser

        _, _, width, height = build(chosen).bounds()
        browser.export(
            document.to_xml(pretty=False),
            output,
            fmt=fmt,
            page=index,
            scale=scale,
            border=border,
            transparent=transparent,
            download=download,
            size=(width, height),
        )
        if fmt == "svg":
            notes.append(
                "HTML labels are foreignObject elements; for SVG read by rsvg-convert, LaTeX or"
                " Inkscape use the native backend"
            )
        if ratio:
            notes.append("aspect padding applies to the native backend only")
        return Result(output, "browser", chosen.id, notes)

    from . import native

    scene = build(chosen)
    unknown = sorted({s.kind for s in scene.shapes if not s.known})
    if unknown:
        notes.append(
            "drawn as rectangles by the native renderer: "
            + ", ".join(unknown)
            + " (use backend='browser' or 'desktop' for exact output)"
        )
    fill = "none" if transparent else background
    if fmt == "svg":
        svg = native.to_svg(scene, border=border, aspect=ratio, background=fill)
        output.write_text(svg, encoding="utf-8")
        return Result(output, "native", chosen.id, notes)
    if fmt == "pdf":
        svg = native.to_svg(scene, border=border, aspect=ratio, background=fill)
        if _vector_pdf(svg, output):
            return Result(output, "native", chosen.id, notes)
        notes.append("PDF is a raster image (install cairosvg or rsvg-convert for vector PDF)")
    image = native.to_image(
        scene,
        scale=scale if fmt != "pdf" else max(scale, 2),
        border=border,
        aspect=ratio,
        background=background,
        transparent=transparent and fmt == "png",
    )
    if fmt == "png":
        image.save(output, "PNG")
    elif fmt == "jpg":
        image.convert("RGB").save(output, "JPEG", quality=92)
    else:
        image.convert("RGB").save(output, "PDF", resolution=96 * max(scale, 2))
    return Result(output, "native", chosen.id, notes)


def render_all(
    source: Union[Document, str, Path], output_dir: Union[str, Path], *, fmt: str = "png", **options
) -> list[Result]:
    """Render every page to `<output_dir>/<page id>.<fmt>`."""
    document = source if isinstance(source, Document) else Document.load(source)
    folder = Path(output_dir).expanduser()
    return [
        render(document, folder / f"{p.id}.{fmt}", page=i, fmt=fmt, **options)
        for i, p in enumerate(document.pages)
    ]


__all__ = ["BACKENDS", "FORMATS", "Result", "render", "render_all"]
