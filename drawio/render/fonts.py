"""Find a TrueType font for raster output on macOS, Windows and Linux.

Order: the DRAWIO_FONT / DRAWIO_FONT_BOLD environment variables, fonts matching the
requested family, common sans-serif fonts that cover Vietnamese and other Latin
scripts, fontconfig (`fc-match`), and finally Pillow's built-in font.
"""

from __future__ import annotations

import functools
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

_DIRS = {
    "darwin": [
        "/System/Library/Fonts/Supplemental",
        "/System/Library/Fonts",
        "/Library/Fonts",
        "~/Library/Fonts",
    ],
    "win32": [
        os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts"),
    ],
    "linux": [
        "/usr/share/fonts",
        "/usr/local/share/fonts",
        "~/.local/share/fonts",
        "~/.fonts",
    ],
}

# File names per style (regular, bold, italic, bold italic), most preferred first.
_SANS = [
    ("Arial.ttf", "Arial Bold.ttf", "Arial Italic.ttf", "Arial Bold Italic.ttf"),
    ("arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf"),
    (
        "LiberationSans-Regular.ttf",
        "LiberationSans-Bold.ttf",
        "LiberationSans-Italic.ttf",
        "LiberationSans-BoldItalic.ttf",
    ),
    (
        "DejaVuSans.ttf",
        "DejaVuSans-Bold.ttf",
        "DejaVuSans-Oblique.ttf",
        "DejaVuSans-BoldOblique.ttf",
    ),
    ("NotoSans-Regular.ttf", "NotoSans-Bold.ttf", "NotoSans-Italic.ttf", "NotoSans-BoldItalic.ttf"),
    ("segoeui.ttf", "segoeuib.ttf", "segoeuii.ttf", "segoeuiz.ttf"),
]
_SERIF = [
    (
        "Times New Roman.ttf",
        "Times New Roman Bold.ttf",
        "Times New Roman Italic.ttf",
        "Times New Roman Bold Italic.ttf",
    ),
    ("times.ttf", "timesbd.ttf", "timesi.ttf", "timesbi.ttf"),
    (
        "LiberationSerif-Regular.ttf",
        "LiberationSerif-Bold.ttf",
        "LiberationSerif-Italic.ttf",
        "LiberationSerif-BoldItalic.ttf",
    ),
    (
        "DejaVuSerif.ttf",
        "DejaVuSerif-Bold.ttf",
        "DejaVuSerif-Italic.ttf",
        "DejaVuSerif-BoldItalic.ttf",
    ),
]
_MONO = [
    (
        "Courier New.ttf",
        "Courier New Bold.ttf",
        "Courier New Italic.ttf",
        "Courier New Bold Italic.ttf",
    ),
    ("cour.ttf", "courbd.ttf", "couri.ttf", "courbi.ttf"),
    (
        "LiberationMono-Regular.ttf",
        "LiberationMono-Bold.ttf",
        "LiberationMono-Italic.ttf",
        "LiberationMono-BoldItalic.ttf",
    ),
    (
        "DejaVuSansMono.ttf",
        "DejaVuSansMono-Bold.ttf",
        "DejaVuSansMono-Oblique.ttf",
        "DejaVuSansMono-BoldOblique.ttf",
    ),
]


def _platform() -> str:
    if sys.platform.startswith("win"):
        return "win32"
    return "darwin" if sys.platform == "darwin" else "linux"


@functools.lru_cache(maxsize=None)
def _files() -> dict[str, str]:
    """Map lower-cased font file names to paths, one directory walk per process."""
    found: dict[str, str] = {}
    for directory in _DIRS[_platform()]:
        root = Path(directory).expanduser()
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.suffix.lower() in (".ttf", ".otf", ".ttc"):
                found.setdefault(path.name.lower(), str(path))
    return found


def _fc_match(family: str, bold: bool, italic: bool) -> Optional[str]:
    if not shutil.which("fc-match"):
        return None
    pattern = family + (":bold" if bold else "") + (":italic" if italic else "")
    try:
        result = subprocess.run(
            ["fc-match", "-f", "%{file}", pattern], capture_output=True, text=True, timeout=5
        )
    except (OSError, subprocess.SubprocessError):
        return None
    path = result.stdout.strip()
    return path if path and Path(path).is_file() else None


@functools.lru_cache(maxsize=64)
def font_path(family: str = "Helvetica", bold: bool = False, italic: bool = False):
    """Path of the font file used for a family and style, or None for Pillow's own font."""
    env = os.environ.get("DRAWIO_FONT_BOLD" if bold else "DRAWIO_FONT") or os.environ.get(
        "DRAWIO_FONT"
    )
    if env and Path(env).is_file():
        return env
    name = (family or "").lower()
    if any(m in name for m in ("courier", "mono", "consolas", "menlo")):
        groups = _MONO + _SANS
    elif "times" in name or ("serif" in name and "sans" not in name):
        groups = _SERIF + _SANS
    else:
        groups = _SANS
    files = _files()
    slot = (2 if italic else 0) + (1 if bold else 0)
    direct = files.get(f"{name}.ttf")
    if direct and not bold and not italic:
        return direct
    for group in groups:
        for candidate in (group[slot], group[1] if bold else group[0], group[0]):
            path = files.get(candidate.lower())
            if path:
                return path
    return _fc_match(family or "sans-serif", bold, italic)


@functools.lru_cache(maxsize=256)
def font(family: str, size: float, *, bold: bool = False, italic: bool = False):
    from PIL import ImageFont

    size = max(1, round(size))
    path = font_path(family, bold, italic)
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1 has no sized default font
        return ImageFont.load_default()


# Fonts with wide symbol coverage, tried for characters the main font lacks.
_FALLBACKS = [
    "Arial Unicode.ttf",
    "Apple Symbols.ttf",
    "arialuni.ttf",
    "seguisym.ttf",
    "segoeui.ttf",
    "DejaVuSans.ttf",
    "NotoSansSymbols2-Regular.ttf",
    "NotoSansSymbols-Regular.ttf",
    "NotoSans-Regular.ttf",
    "FreeSans.ttf",
]


@functools.lru_cache(maxsize=64)
def fallbacks(size: float) -> tuple:
    from PIL import ImageFont

    out = []
    files = _files()
    for name in _FALLBACKS:
        path = files.get(name.lower())
        if path:
            try:
                out.append(ImageFont.truetype(path, max(1, round(size))))
            except OSError:
                continue
    return tuple(out)


_MISSING_PROBE = "\U0010fffd"  # a private-use code point no font draws


@functools.lru_cache(maxsize=4096)
def _missing(face, ch: str) -> bool:
    """Whether `face` lacks a glyph for ch: it then draws the same box as for the probe."""
    if ch.isspace() or not hasattr(face, "getmask"):
        return False
    try:
        glyph, probe = face.getmask(ch), face.getmask(_MISSING_PROBE)
    except Exception:
        return False
    return glyph.size == probe.size and bytes(glyph) == bytes(probe)


def runs(face, text: str, size: float) -> list:
    """Split text into (font, chunk) runs, swapping in a fallback font where needed."""
    out: list = []
    for ch in text:
        chosen = face
        if _missing(face, ch):
            for other in fallbacks(size):
                if not _missing(other, ch):
                    chosen = other
                    break
        if out and out[-1][0] is chosen:
            out[-1][1] += ch
        else:
            out.append([chosen, ch])
    return out
