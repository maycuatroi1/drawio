"""Estimate how much room a label needs, without fonts or third-party packages.

Widths come from the Adobe core font metrics for Helvetica, which Arial matches,
so a label measured here wraps close to where draw.io wraps it. Accented Latin
letters (Vietnamese included) take the width of their base letter. The result is
an estimate: it is meant to catch labels that clearly do not fit, not to place
glyphs to the pixel.
"""

from __future__ import annotations

import html
import re
import unicodedata

# Advance widths in 1/1000 em for ASCII 32..126.
_REGULAR = (
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
    1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
    333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
    556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584,
)  # fmt: skip
_BOLD = (
    278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611,
    975, 722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584, 556,
    333, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611,
    611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584,
)  # fmt: skip
_AVERAGE = 556
LINE_HEIGHT = 1.2  # draw.io's mxConstants.LINE_HEIGHT
_TAG = re.compile(r"<[^>]*>")
_SPACES = re.compile(r"[ \t]+")
_BREAK = re.compile(r"<\s*br\s*/?\s*>|</\s*(?:div|p|li|h[1-6])\s*>", re.IGNORECASE)


def _family_factor(family: str) -> float:
    family = (family or "").lower()
    if any(name in family for name in ("courier", "mono", "consolas", "menlo")):
        return -1.0  # every character is 0.6 em
    if "times" in family or ("serif" in family and "sans" not in family):
        return 0.9
    return 1.0


def char_width(ch: str, *, bold: bool = False, family: str = "Helvetica") -> float:
    """Advance width of one character in em."""
    factor = _family_factor(family)
    if factor < 0:
        return 0.6
    code = ord(ch)
    if not 32 <= code <= 126:
        if unicodedata.combining(ch):
            return 0.0
        if unicodedata.east_asian_width(ch) in ("W", "F"):
            return 1.0
        base = unicodedata.normalize("NFD", ch)[:1]
        code = ord(base) if base else 0
        if not 32 <= code <= 126:
            return factor * _AVERAGE / 1000
    table = _BOLD if bold else _REGULAR
    return factor * table[code - 32] / 1000


def text_width(text: str, size: float, *, bold: bool = False, family: str = "Helvetica") -> float:
    """Width in pixels of one line of text at font size `size`."""
    return sum(char_width(c, bold=bold, family=family) for c in text) * size


def plain(value: str, *, html_label: bool = False) -> str:
    """The text a label shows: HTML breaks become newlines, and runs of spaces collapse to
    one space, as draw.io displays them."""
    if html_label:
        value = _BREAK.sub("\n", value.replace("\r", "").replace("\n", " "))
        value = html.unescape(_TAG.sub("", value))
    lines = [_SPACES.sub(" ", line).strip(" \t") for line in value.split("\n")]
    return "\n".join(lines).replace("\xa0", " ").strip("\n")


def wrap(
    text: str,
    width: float,
    size: float,
    *,
    bold: bool = False,
    family: str = "Helvetica",
) -> list[str]:
    """Break text into lines no wider than `width`, splitting long words if needed."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split(" "):
            candidate = word if not line else f"{line} {word}"
            if text_width(candidate, size, bold=bold, family=family) <= width or not line:
                line = candidate
            else:
                lines.append(line)
                line = word
            # A single word wider than the box breaks at characters, as draw.io does.
            while text_width(line, size, bold=bold, family=family) > width and len(line) > 1:
                cut = len(line) - 1
                while cut > 1 and text_width(line[:cut], size, bold=bold, family=family) > width:
                    cut -= 1
                lines.append(line[:cut])
                line = line[cut:]
        lines.append(line)
    return lines


def measure(
    text: str,
    size: float,
    *,
    width: float | None = None,
    bold: bool = False,
    family: str = "Helvetica",
) -> tuple[float, float, list[str]]:
    """Return (width, height, lines) of a label, wrapped at `width` when given."""
    lines = wrap(text, width, size, bold=bold, family=family) if width else text.split("\n")
    widest = max((text_width(line, size, bold=bold, family=family) for line in lines), default=0)
    return widest, len(lines) * size * LINE_HEIGHT, lines


def longest_word(text: str, size: float, *, bold: bool = False, family: str = "Helvetica"):
    """Width of the widest unbreakable word, the narrowest a wrapped label can get."""
    words = text.split()
    return max((text_width(w, size, bold=bold, family=family) for w in words), default=0)
