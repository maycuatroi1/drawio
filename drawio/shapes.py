"""Named draw.io shapes and the colour presets of the editor's Style panel."""

from __future__ import annotations

# Style properties that turn a plain box into a built-in draw.io shape. Sizes are
# written out so the native renderer and draw.io agree on the proportions.
SHAPES: dict[str, dict] = {
    "rectangle": {},
    "rounded": {"rounded": 1},
    "ellipse": {"shape": "ellipse", "perimeter": "ellipsePerimeter"},
    "circle": {"shape": "ellipse", "perimeter": "ellipsePerimeter", "aspect": "fixed"},
    "rhombus": {"shape": "rhombus", "perimeter": "rhombusPerimeter"},
    "diamond": {"shape": "rhombus", "perimeter": "rhombusPerimeter"},
    "cylinder": {"shape": "cylinder3", "boundedLbl": 1, "backgroundOutline": 1, "size": 15},
    "hexagon": {"shape": "hexagon", "perimeter": "hexagonPerimeter2", "size": 0.25},
    "triangle": {"shape": "triangle", "perimeter": "trianglePerimeter"},
    "parallelogram": {
        "shape": "parallelogram",
        "perimeter": "parallelogramPerimeter",
        "size": 0.2,
    },
    "document": {"shape": "document", "boundedLbl": 1, "size": 0.3},
    "cloud": {"shape": "cloud"},
    "process": {"shape": "process", "backgroundOutline": 1, "size": 0.1},
    "note": {"shape": "note", "backgroundOutline": 1, "size": 20},
    "card": {"shape": "card", "size": 20},
    "step": {"shape": "step", "perimeter": "stepPerimeter", "size": 0.2},
    "actor": {
        "shape": "umlActor",
        "verticalLabelPosition": "bottom",
        "verticalAlign": "top",
        "outlineConnect": 0,
    },
}

# The fill and line pairs offered in draw.io's Style panel.
PALETTE: dict[str, dict] = {
    "white": {"fillColor": "#ffffff", "strokeColor": "#000000"},
    "gray": {"fillColor": "#f5f5f5", "strokeColor": "#666666", "fontColor": "#333333"},
    "blue": {"fillColor": "#dae8fc", "strokeColor": "#6c8ebf"},
    "green": {"fillColor": "#d5e8d4", "strokeColor": "#82b366"},
    "orange": {"fillColor": "#ffe6cc", "strokeColor": "#d79b00"},
    "yellow": {"fillColor": "#fff2cc", "strokeColor": "#d6b656"},
    "red": {"fillColor": "#f8cecc", "strokeColor": "#b85450"},
    "purple": {"fillColor": "#e1d5e7", "strokeColor": "#9673a6"},
}

# Connector ends draw.io understands, for Page.connect(arrow=..., start_arrow=...).
ARROWS = (
    "none",
    "block",
    "classic",
    "open",
    "oval",
    "diamond",
    "blockThin",
    "classicThin",
    "openThin",
    "ERone",
    "ERmany",
    "ERmandOne",
    "ERoneToMany",
    "ERzeroToOne",
    "ERzeroToMany",
)


def style_for(shape: str | None) -> dict:
    """Style properties for a shape name from SHAPES, or for a raw draw.io shape."""
    if shape is None:
        return {}
    if shape in SHAPES:
        return dict(SHAPES[shape])
    return {"shape": shape}


def color(name: str) -> dict:
    """Fill, line (and text) colours of a Style panel preset, e.g. color("blue")."""
    try:
        return dict(PALETTE[name])
    except KeyError as exc:
        raise ValueError(f"Unknown colour preset {name!r}; choose from {sorted(PALETTE)}") from exc
