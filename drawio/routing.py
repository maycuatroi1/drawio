# This file is a Python port of connector routing from mxGraph (mxEdgeStyle, mxPerimeter
# and parts of mxGraphView), as shipped in the diagrams.net viewer.
#
# Copyright (c) 2006-2020, JGraph Ltd
# Copyright (c) 2006-2020, draw.io AG
# Port: Copyright (c) 2026, drawio-python contributors
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not use this
# file except in compliance with the License. A copy is in LICENSES/Apache-2.0.txt and at
# http://www.apache.org/licenses/LICENSE-2.0. Unless required by applicable law or agreed
# to in writing, software distributed under the License is distributed on an "AS IS"
# BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#
# Changes from the original: translated to Python; works on plain (x, y, w, h) boxes at
# scale 1; no rotation, flipping, port constraints or channel bounds; draws no shapes.
"""Where draw.io draws a connector: the routers and perimeters of mxGraph, ported.

`route()` returns the polyline draw.io computes for straight connectors, elbowEdgeStyle,
orthogonalEdgeStyle (OrthConnector, and SegmentConnector once a connector has waypoints),
including where unpinned ends meet the outline of their shape.
"""

from __future__ import annotations

import math
from typing import Optional

Point = tuple[float, float]
Box = tuple[float, float, float, float]

WEST, NORTH, SOUTH, EAST, ALL = 1, 2, 4, 8, 15
_SIDE_DIR = {"left": WEST, "top": NORTH, "bottom": SOUTH, "right": EAST}
_ORTH_BUFFER = 10
_DIR_VECTORS = [[-1, 0], [0, -1], [1, 0], [0, 1], [-1, 0], [0, -1], [1, 0]]
_ROUTE_PATTERNS = [
    [
        [513, 2308, 2081, 2562],
        [513, 1090, 514, 2184, 2114, 2561],
        [513, 1090, 514, 2564, 2184, 2562],
        [513, 2308, 2561, 1090, 514, 2568, 2308],
    ],
    [
        [514, 1057, 513, 2308, 2081, 2562],
        [514, 2184, 2114, 2561],
        [514, 2184, 2562, 1057, 513, 2564, 2184],
        [514, 1057, 513, 2568, 2308, 2561],
    ],
    [
        [1090, 514, 1057, 513, 2308, 2081, 2562],
        [2114, 2561],
        [1090, 2562, 1057, 513, 2564, 2184],
        [1090, 514, 1057, 513, 2308, 2561, 2568],
    ],
    [
        [2081, 2562],
        [1057, 513, 1090, 514, 2184, 2114, 2561],
        [1057, 513, 1090, 514, 2184, 2562, 2564],
        [1057, 2561, 1090, 514, 2568, 2308],
    ],
]
_SIDE_MASK, _CENTER_MASK, _SOURCE_MASK, _TARGET_MASK = 480, 512, 1024, 2048


def _reverse(direction: int) -> int:
    return (
        ((direction & WEST) << 3)
        | ((direction & NORTH) << 1)
        | ((direction & SOUTH) >> 1)
        | ((direction & EAST) >> 3)
    )


def _contains(box: Optional[Box], x: float, y: float) -> bool:
    return box is not None and box[0] <= x <= box[0] + box[2] and box[1] <= y <= box[1] + box[3]


def _centre(box: Box) -> Point:
    return box[0] + box[2] / 2, box[1] + box[3] / 2


# ------------------------------------------------------------------ perimeters


def _rectangle(box: Box, nxt: Point, orthogonal: bool) -> Point:
    x, y, w, h = box
    cx, cy = _centre(box)
    alpha = math.atan2(nxt[1] - cy, nxt[0] - cx)
    beta = math.pi / 2 - alpha
    t = math.atan2(h, w)
    if alpha < -math.pi + t or alpha > math.pi - t:
        px, py = x, cy - w * math.tan(alpha) / 2
    elif alpha < -t:
        px, py = cx - h * math.tan(beta) / 2, y
    elif alpha < t:
        px, py = x + w, cy + w * math.tan(alpha) / 2
    else:
        px, py = cx + h * math.tan(beta) / 2, y + h
    if orthogonal:
        if x <= nxt[0] <= x + w:
            px = nxt[0]
        elif y <= nxt[1] <= y + h:
            py = nxt[1]
        if nxt[0] < x:
            px = x
        elif nxt[0] > x + w:
            px = x + w
        if nxt[1] < y:
            py = y
        elif nxt[1] > y + h:
            py = y + h
    return px, py


def _ellipse(box: Box, nxt: Point, orthogonal: bool) -> Point:
    x, y, w, h = box
    a, b = w / 2, h / 2
    cx, cy = x + a, y + b
    px, py = nxt
    dx, dy = int(px - cx), int(py - cy)  # parseInt in the original truncates
    if dx == 0 and dy != 0:
        return cx, cy + b * dy / abs(dy)
    if dx == 0 and dy == 0:
        return px, py
    if orthogonal:
        if y <= py <= y + h:
            ty = py - cy
            tx = math.sqrt(max(a * a * (1 - ty * ty / (b * b)), 0)) if b else 0
            if px <= x:
                tx = -tx
            return cx + tx, py
        if x <= px <= x + w:
            tx = px - cx
            ty = math.sqrt(max(b * b * (1 - tx * tx / (a * a)), 0)) if a else 0
            if py <= y:
                ty = -ty
            return px, cy + ty
    e = a * b / math.sqrt(b * b * dx * dx + a * a * dy * dy)
    return cx + e * dx, cy + e * dy


def _intersection(x0, y0, x1, y1, x2, y2, x3, y3) -> Optional[Point]:
    denom = (y3 - y2) * (x1 - x0) - (x3 - x2) * (y1 - y0)
    if denom == 0:
        return None
    ua = ((x3 - x2) * (y0 - y2) - (y3 - y2) * (x0 - x2)) / denom
    ub = ((x1 - x0) * (y0 - y2) - (y1 - y0) * (x0 - x2)) / denom
    if 0 <= ua <= 1 and 0 <= ub <= 1:
        return x0 + ua * (x1 - x0), y0 + ua * (y1 - y0)
    return None


def _rhombus(box: Box, nxt: Point, orthogonal: bool) -> Point:
    x, y, w, h = box
    cx, cy = x + w / 2, y + h / 2
    px, py = nxt
    if cx == px:
        return (cx, y) if cy > py else (cx, y + h)
    if cy == py:
        return (x, cy) if cx > px else (x + w, cy)
    tx, ty = cx, cy
    if orthogonal:
        if x <= px <= x + w:
            tx = px
        elif y <= py <= y + h:
            ty = py
    if px < cx:
        hit = (
            _intersection(px, py, tx, ty, cx, y, x, cy)
            if py < cy
            else _intersection(px, py, tx, ty, cx, y + h, x, cy)
        )
    else:
        hit = (
            _intersection(px, py, tx, ty, cx, y, x + w, cy)
            if py < cy
            else _intersection(px, py, tx, ty, cx, y + h, x + w, cy)
        )
    return hit if hit is not None else (cx, cy)


def perimeter(box: Box, nxt: Point, kind: str = "rectangle", orthogonal: bool = False) -> Point:
    """The point where a connector heading for `nxt` meets the outline of a shape."""
    if box[2] <= 0 and box[3] <= 0:
        return box[0], box[1]
    if kind == "ellipse":
        return _ellipse(box, nxt, orthogonal)
    if kind == "rhombus":
        return _rhombus(box, nxt, orthogonal)
    return _rectangle(box, nxt, orthogonal)


def port_point(box: Box, fx: float, fy: float, kind: str = "rectangle") -> Point:
    """A fixed connection point (exitX/exitY or entryX/entryY), projected onto the outline."""
    point = (box[0] + fx * box[2], box[1] + fy * box[3])
    return perimeter(box, point, kind, False)


# ------------------------------------------------------------------ routers


def _segment(
    source: Optional[Box],
    target: Optional[Box],
    hints: list[Point],
    p0: Optional[Point],
    pe: Optional[Point],
) -> list[Point]:
    """mxEdgeStyle.SegmentConnector."""
    result: list[list[float]] = []
    horizontal = True
    t = list(p0) if p0 else (list(_centre(source)) if source else None)
    d: Optional[list[float]] = None
    if hints:
        u = [list(h) for h in hints]
        if t is not None:
            if abs(u[0][0] - t[0]) < 1:
                u[0][0] = t[0]
            if abs(u[0][1] - t[1]) < 1:
                u[0][1] = t[1]
        if pe is not None:
            if abs(u[-1][0] - pe[0]) < 1:
                u[-1][0] = pe[0]
            if abs(u[-1][1] - pe[1]) < 1:
                u[-1][1] = pe[1]
        d = u[0]
        term, chan, current, hint = source, source, p0, d
        if current is not None:
            term = None
        for i in range(2):
            fixed_v = current is not None and current[0] == hint[0]
            fixed_h = current is not None and current[1] == hint[1]
            in_h = term is not None and chan[1] <= hint[1] <= chan[1] + chan[3]
            in_v = term is not None and chan[0] <= hint[0] <= chan[0] + chan[2]
            h_chan = fixed_h or (current is None and in_h)
            v_chan = fixed_v or (current is None and in_v)
            if not (i == 0 and ((h_chan and v_chan) or (fixed_v and fixed_h))):
                if current is not None and not fixed_h and not fixed_v and (in_h or in_v):
                    horizontal = not in_h
                    break
                if v_chan or h_chan:
                    horizontal = h_chan
                    if i == 1:
                        horizontal = h_chan if len(u) % 2 == 0 else v_chan
                    break
            term, chan, current = target, target, pe
            if current is not None:
                term = None
            hint = u[-1]
            if fixed_v and fixed_h:
                u = u[1:]
        if horizontal and (
            (p0 is not None and p0[1] != d[1])
            or (
                p0 is None and source is not None and not source[1] <= d[1] <= source[1] + source[3]
            )
        ):
            result.append([t[0], d[1]])
        elif not horizontal and (
            (p0 is not None and p0[0] != d[0])
            or (
                p0 is None and source is not None and not source[0] <= d[0] <= source[0] + source[2]
            )
        ):
            result.append([d[0], t[1]])
        if horizontal:
            t[1] = d[1]
        else:
            t[0] = d[0]
        for hint in u:
            horizontal = not horizontal
            d = hint
            if horizontal:
                t[1] = d[1]
            else:
                t[0] = d[0]
            result.append(list(t))
    else:
        d = t
        horizontal = True
    end = list(pe) if pe else (list(_centre(target)) if target else None)
    if end is not None and d is not None:
        if horizontal and (
            (pe is not None and pe[1] != d[1])
            or (
                pe is None and target is not None and not target[1] <= d[1] <= target[1] + target[3]
            )
        ):
            result.append([end[0], d[1]])
        elif not horizontal and (
            (pe is not None and pe[0] != d[0])
            or (
                pe is None and target is not None and not target[0] <= d[0] <= target[0] + target[2]
            )
        ):
            result.append([d[0], end[1]])
    if p0 is None and source is not None:
        while result and _contains(source, *result[0]):
            result.pop(0)
    if pe is None and target is not None:
        while result and _contains(target, *result[-1]):
            result.pop()
    out: list[list[float]] = []
    last = list(p0) if p0 is not None else None
    for p in result:
        p = [round(p[0] * 10) / 10, round(p[1] * 10) / 10]
        if last is None or abs(last[0] - p[0]) >= 1 or abs(last[1] - p[1]) >= 1:
            out.append(p)
            last = p
    if pe is not None and out and abs(pe[0] - out[-1][0]) <= 1 and abs(pe[1] - out[-1][1]) <= 1:
        out.pop()
        if out:
            if abs(out[-1][0] - pe[0]) < 1:
                out[-1][0] = pe[0]
            if abs(out[-1][1] - pe[1]) < 1:
                out[-1][1] = pe[1]
    return [(p[0], p[1]) for p in out]


def _jetty(style: dict, source: bool) -> float:
    value = style.get("sourceJettySize" if source else "targetJettySize")
    if value is None:
        value = style.get("jettySize", _ORTH_BUFFER)
    if value == "auto":
        arrow = style.get("startArrow" if source else "endArrow", "none")
        if arrow and arrow != "none":
            size = float(style.get("startSize" if source else "endSize", 6))
            return max(2, math.ceil((size + _ORTH_BUFFER) / _ORTH_BUFFER)) * _ORTH_BUFFER
        return 2 * _ORTH_BUFFER
    try:
        return float(value)
    except (TypeError, ValueError):
        return _ORTH_BUFFER


def _orth(
    source: Box,
    target: Box,
    style: dict,
    p0: Optional[Point],
    pe: Optional[Point],
) -> list[Point]:
    """mxEdgeStyle.OrthConnector for two shapes and no waypoints."""
    u, x_buf = _jetty(style, True), _jetty(style, False)
    if source == target:
        u = x_buf = max(u, x_buf)
    total = u + x_buf
    if p0 is not None and pe is not None:
        if (pe[0] - p0[0]) ** 2 + (pe[1] - p0[1]) ** 2 < total * total:
            return _segment(source, target, [], p0, pe)
    constraint = [ALL, ALL]
    geo = [list(source), list(target)]
    if not (geo[0][2] and geo[0][3] and geo[1][2] and geo[1][3]):
        return []
    buffers = [u, x_buf]
    limits = [[0.0] * 9, [0.0] * 9]
    for i in range(2):
        limits[i][1] = geo[i][0] - buffers[i]
        limits[i][2] = geo[i][1] - buffers[i]
        limits[i][4] = geo[i][0] + geo[i][2] + buffers[i]
        limits[i][8] = geo[i][1] + geo[i][3] + buffers[i]
    dx = (geo[0][0] + geo[0][2] / 2) - (geo[1][0] + geo[1][2] / 2)
    dy = (geo[0][1] + geo[0][3] / 2) - (geo[1][1] + geo[1][3] / 2)
    quad = 0
    if dx < 0:
        quad = 2 if dy < 0 else 1
    elif dy <= 0:
        quad = 3
        if dx == 0:
            quad = 2
    direction = [0, 0]
    rel = [[0.5, 0.5], [0.5, 0.5]]
    for i, point in enumerate((p0, pe)):
        if point is None:
            continue
        rel[i][0] = (point[0] - geo[i][0]) / geo[i][2]
        if abs(point[0] - geo[i][0]) <= 1:
            direction[i] = WEST
        elif abs(point[0] - geo[i][0] - geo[i][2]) <= 1:
            direction[i] = EAST
        rel[i][1] = (point[1] - geo[i][1]) / geo[i][3]
        if abs(point[1] - geo[i][1]) <= 1:
            direction[i] = NORTH
        elif abs(point[1] - geo[i][1] - geo[i][3]) <= 1:
            direction[i] = SOUTH
    top = geo[0][1] - (geo[1][1] + geo[1][3])
    left = geo[0][0] - (geo[1][0] + geo[1][2])
    bottom = geo[1][1] - (geo[0][1] + geo[0][3])
    right = geo[1][0] - (geo[0][0] + geo[0][2])
    separations = [0.0] * 5
    separations[1] = max(left - total, 0)
    separations[2] = max(top - total, 0)
    separations[4] = max(bottom - total, 0)
    separations[3] = max(right - total, 0)
    hor = [WEST if left >= right else EAST, 0]
    ver = [NORTH if top >= bottom else SOUTH, 0]
    hor[1], ver[1] = _reverse(hor[0]), _reverse(ver[0])
    pref_h = left if left >= right else right
    pref_v = top if top >= bottom else bottom
    order = [[0, 0], [0, 0]]
    chosen = False
    for i in range(2):
        if direction[i] != 0:
            continue
        if hor[i] & constraint[i] == 0:
            hor[i] = _reverse(hor[i])
        if ver[i] & constraint[i] == 0:
            ver[i] = _reverse(ver[i])
        order[i] = [ver[i], hor[i]]
    if pref_v > 0 and pref_h > 0:
        if hor[0] & constraint[0] and ver[1] & constraint[1]:
            order = [[hor[0], ver[0]], [ver[1], hor[1]]]
            chosen = True
        elif ver[0] & constraint[0] and hor[1] & constraint[1]:
            order = [[ver[0], hor[0]], [hor[1], ver[1]]]
            chosen = True
    if pref_v > 0 and not chosen:
        order = [[ver[0], hor[0]], [ver[1], hor[1]]]
        chosen = True
    if pref_h > 0 and not chosen:
        order = [[hor[0], ver[0]], [hor[1], ver[1]]]
    for i in range(2):
        if direction[i] != 0:
            continue
        if order[i][0] & constraint[i] == 0:
            order[i][0] = order[i][1]
        pref = order[i][0] & constraint[i]
        pref |= (order[i][1] & constraint[i]) << 8
        pref |= (order[1 - i][i] & constraint[i]) << 16
        pref |= (order[1 - i][1 - i] & constraint[i]) << 24
        if pref & 15 == 0:
            pref <<= 8
        if pref & 3840 == 0:
            pref = (pref & 15) | (pref >> 8)
        if pref & 983040 == 0:
            pref = (pref & 65535) | ((pref & 251658240) >> 8)
        direction[i] = pref & 15
    s_index = 3 if direction[0] == EAST else direction[0]
    t_index = 3 if direction[1] == EAST else direction[1]
    s_index -= quad
    t_index -= quad
    if s_index < 1:
        s_index += 4
    if t_index < 1:
        t_index += 4
    pattern = _ROUTE_PATTERNS[s_index - 1][t_index - 1]
    wp = [[0.0, 0.0] for _ in range(12)]
    wp[0] = [geo[0][0], geo[0][1]]
    if direction[0] == WEST:
        wp[0][0] -= u
        wp[0][1] += rel[0][1] * geo[0][3]
    elif direction[0] == SOUTH:
        wp[0][0] += rel[0][0] * geo[0][2]
        wp[0][1] += geo[0][3] + u
    elif direction[0] == EAST:
        wp[0][0] += geo[0][2] + u
        wp[0][1] += rel[0][1] * geo[0][3]
    elif direction[0] == NORTH:
        wp[0][0] += rel[0][0] * geo[0][2]
        wp[0][1] -= u
    current = 0
    last = initial = 0 if direction[0] & (EAST | WEST) else 1
    for step in pattern:
        nxt = step & 15
        index = 3 if nxt == EAST else nxt
        index += quad
        if index > 4:
            index -= 4
        vector = _DIR_VECTORS[index - 1]
        orientation = 0 if index % 2 > 0 else 1
        if orientation != last:
            current += 1
            wp[current] = list(wp[current - 1])
        to_target = step & _TARGET_MASK > 0
        to_source = step & _SOURCE_MASK > 0
        side = (step & _SIDE_MASK) >> 5
        side <<= quad
        if side > 15:
            side >>= 4
        centre = step & _CENTER_MASK > 0
        if (to_source or to_target) and side < 9:
            which = 0 if to_source else 1
            if centre and orientation == 0:
                limit = geo[which][0] + rel[which][0] * geo[which][2]
            elif centre:
                limit = geo[which][1] + rel[which][1] * geo[which][3]
            else:
                limit = limits[which][side]
            if orientation == 0:
                move = (limit - wp[current][0]) * vector[0]
                if move > 0:
                    wp[current][0] += vector[0] * move
            else:
                move = (limit - wp[current][1]) * vector[1]
                if move > 0:
                    wp[current][1] += vector[1] * move
        elif centre:
            wp[current][0] += vector[0] * abs(separations[index] / 2)
            wp[current][1] += vector[1] * abs(separations[index] / 2)
        if current > 0 and wp[current][orientation] == wp[current - 1][orientation]:
            current -= 1
        else:
            last = orientation
    target_orientation = 0 if direction[1] & (EAST | WEST) else 1
    out: list[Point] = []
    for i in range(current + 1):
        if i == current and (0 if target_orientation == initial else 1) != (current + 1) % 2:
            break
        out.append((round(wp[i][0] * 10) / 10, round(wp[i][1] * 10) / 10))
    deduped: list[Point] = []
    for p in out:
        previous = deduped[-1] if deduped else p0
        if previous is None or previous != p:
            deduped.append(p)
    return deduped


def _side_to_side(source: Box, target: Box, hint: Optional[Point], p0, pe) -> list[Point]:
    """mxEdgeStyle.SideToSide."""
    if p0 is not None:
        source = (p0[0], p0[1], 0, 0)
    if pe is not None:
        target = (pe[0], pe[1], 0, 0)
    lo = max(source[0], target[0])
    hi = min(source[0] + source[2], target[0] + target[2])
    x = hint[0] if hint else round(hi + (lo - hi) / 2)
    y1, y2 = _centre(source)[1], _centre(target)[1]
    if hint:
        if source[1] <= hint[1] <= source[1] + source[3]:
            y1 = hint[1]
        if target[1] <= hint[1] <= target[1] + target[3]:
            y2 = hint[1]
    out: list[Point] = []
    if not _contains(target, x, y1) and not _contains(source, x, y1):
        out.append((x, y1))
    if not _contains(target, x, y2) and not _contains(source, x, y2):
        out.append((x, y2))
    # draw.io's result array already holds the source end, so its "one point" test means
    # that no bend was added.
    if not out:
        if hint:
            if not _contains(target, x, hint[1]) and not _contains(source, x, hint[1]):
                out.append((x, hint[1]))
        else:
            top = max(source[1], target[1])
            out.append((x, top + (min(source[1] + source[3], target[1] + target[3]) - top) / 2))
    return out


def _top_to_bottom(source: Box, target: Box, hint: Optional[Point], p0, pe) -> list[Point]:
    """mxEdgeStyle.TopToBottom."""
    if p0 is not None:
        source = (p0[0], p0[1], 0, 0)
    if pe is not None:
        target = (pe[0], pe[1], 0, 0)
    lo = max(source[1], target[1])
    hi = min(source[1] + source[3], target[1] + target[3])
    x = _centre(source)[0]
    if hint and source[0] <= hint[0] <= source[0] + source[2]:
        x = hint[0]
    y = hint[1] if hint else round(hi + (lo - hi) / 2)
    out: list[Point] = []
    if not _contains(target, x, y) and not _contains(source, x, y):
        out.append((x, y))
    x = hint[0] if hint and target[0] <= hint[0] <= target[0] + target[2] else _centre(target)[0]
    if not _contains(target, x, y) and not _contains(source, x, y):
        out.append((x, y))
    if not out:
        if hint:
            if not _contains(target, hint[0], y) and not _contains(source, hint[0], y):
                out.append((hint[0], y))
        else:
            left = max(source[0], target[0])
            out.append((left + (min(source[0] + source[2], target[0] + target[2]) - left) / 2, y))
    return out


def _elbow(source: Box, target: Box, style: dict, hints: list[Point], p0, pe) -> list[Point]:
    """mxEdgeStyle.ElbowConnector."""
    hint = hints[0] if hints else None
    vertical = horizontal = False
    if hint is not None:
        left = min(source[0], target[0])
        right = max(source[0] + source[2], target[0] + target[2])
        top = min(source[1], target[1])
        bottom = max(source[1] + source[3], target[1] + target[3])
        vertical = hint[1] < top or hint[1] > bottom
        horizontal = hint[0] < left or hint[0] > right
    else:
        left = max(source[0], target[0])
        right = min(source[0] + source[2], target[0] + target[2])
        vertical = left == right
        if not vertical:
            top = max(source[1], target[1])
            bottom = min(source[1] + source[3], target[1] + target[3])
            horizontal = bottom == top
    if horizontal or (not vertical and style.get("elbow") != "vertical"):
        return _side_to_side(source, target, hint, p0, pe)
    return _top_to_bottom(source, target, hint, p0, pe)


_ORTHOGONAL = {
    "orthogonalEdgeStyle",
    "elbowEdgeStyle",
    "segmentEdgeStyle",
    "sideToSideEdgeStyle",
    "topToBottomEdgeStyle",
    "entityRelationEdgeStyle",
}


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
    """The polyline draw.io draws for a connector, from its source to its target end."""

    def num(key: str) -> Optional[float]:
        try:
            return float(style[key])
        except (KeyError, TypeError, ValueError):
            return None

    p0 = pe = None
    if source is not None and num("exitX") is not None and num("exitY") is not None:
        p0 = port_point(source, num("exitX"), num("exitY"), source_kind)
    elif source is None:
        p0 = source_point or (0.0, 0.0)
    if target is not None and num("entryX") is not None and num("entryY") is not None:
        pe = port_point(target, num("entryX"), num("entryY"), target_kind)
    elif target is None:
        pe = target_point or (0.0, 0.0)
    edge_style = style.get("edgeStyle") or "none"
    orthogonal = edge_style in _ORTHOGONAL
    if orthogonal and "orthogonal" in style:
        orthogonal = style.get("orthogonal") == "1"
    waypoints = [tuple(p) for p in waypoints]
    if edge_style == "orthogonalEdgeStyle" and source is not None and target is not None:
        if waypoints:
            bends = _segment(source, target, waypoints, p0, pe)
        else:
            bends = _orth(source, target, style, p0, pe)
    elif edge_style == "segmentEdgeStyle":
        bends = _segment(source, target, waypoints, p0, pe)
    elif edge_style == "elbowEdgeStyle" and source is not None and target is not None:
        bends = _elbow(source, target, style, waypoints, p0, pe)
    elif edge_style == "sideToSideEdgeStyle" and source is not None and target is not None:
        bends = _side_to_side(source, target, waypoints[0] if waypoints else None, p0, pe)
    elif edge_style == "topToBottomEdgeStyle" and source is not None and target is not None:
        bends = _top_to_bottom(source, target, waypoints[0] if waypoints else None, p0, pe)
    elif orthogonal and waypoints:
        bends = _segment(source, target, waypoints, p0, pe)
    else:
        bends = list(waypoints)
    # mxGraphView.updateFloatingTerminalPoints: the target end first, then the source end.
    end = pe
    if end is None:
        nxt = bends[-1] if bends else (p0 if p0 is not None else _centre(source))
        end = perimeter(target, nxt, target_kind, orthogonal)
    start = p0
    if start is None:
        nxt = bends[0] if bends else end
        start = perimeter(source, nxt, source_kind, orthogonal)
    points = [start, *bends, end]
    out: list[Point] = []
    for p in points:
        p = (round(p[0], 2), round(p[1], 2))
        if out and abs(out[-1][0] - p[0]) < 0.01 and abs(out[-1][1] - p[1]) < 0.01:
            continue
        out.append(p)
    return out
