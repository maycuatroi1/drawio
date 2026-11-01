"""Place shapes automatically, so a script does not have to compute coordinates.

All functions move existing shapes. Shapes passed together must share a parent; their
coordinates stay relative to it. Run `page.fit()` afterwards to grow containers and the
page around the result.
"""

from __future__ import annotations

from typing import Iterable, Optional, Sequence, Union

from .document import Cell, Page

_DIRECTIONS = {"down", "up", "right", "left"}


def _start(cells: Sequence[Cell], x: Optional[float], y: Optional[float]):
    return (cells[0].x if x is None else x), (cells[0].y if y is None else y)


def _offset(size: float, room: float, align: str) -> float:
    if align in ("start", "left", "top"):
        return 0.0
    if align in ("end", "right", "bottom"):
        return room - size
    return (room - size) / 2


def row(
    cells: Sequence[Cell],
    *,
    x: Optional[float] = None,
    y: Optional[float] = None,
    gap: float = 40,
    align: str = "center",
) -> None:
    """Line shapes up left to right, `gap` apart; align is "top", "center" or "bottom"."""
    if not cells:
        return
    x, y = _start(cells, x, y)
    tallest = max(c.height for c in cells)
    for cell in cells:
        cell.move(x, y + _offset(cell.height, tallest, align))
        x += cell.width + gap


def column(
    cells: Sequence[Cell],
    *,
    x: Optional[float] = None,
    y: Optional[float] = None,
    gap: float = 40,
    align: str = "center",
) -> None:
    """Stack shapes top to bottom, `gap` apart; align is "left", "center" or "right"."""
    if not cells:
        return
    x, y = _start(cells, x, y)
    widest = max(c.width for c in cells)
    for cell in cells:
        cell.move(x + _offset(cell.width, widest, align), y)
        y += cell.height + gap


def grid(
    cells: Sequence[Cell],
    columns: int,
    *,
    x: Optional[float] = None,
    y: Optional[float] = None,
    gap: Union[float, tuple[float, float]] = 40,
) -> None:
    """Arrange shapes in a grid of `columns` columns, each cell centred in its slot."""
    if columns < 1:
        raise ValueError("A grid needs at least one column")
    if not cells:
        return
    gap_x, gap_y = gap if isinstance(gap, tuple) else (gap, gap)
    x, y = _start(cells, x, y)
    rows = [cells[i : i + columns] for i in range(0, len(cells), columns)]
    widths = [max(c.width for c in cells[i::columns]) for i in range(min(columns, len(cells)))]
    top = y
    for line in rows:
        height = max(c.height for c in line)
        left = x
        for i, cell in enumerate(line):
            cell.move(
                left + _offset(cell.width, widths[i], "center"),
                top + _offset(cell.height, height, "center"),
            )
            left += widths[i] + gap_x
        top += height + gap_y


def layered(
    page: Page,
    cells: Optional[Iterable[Cell]] = None,
    *,
    direction: str = "down",
    rank_gap: float = 80,
    gap: float = 40,
    x: float = 40,
    y: float = 40,
    ports: bool = True,
) -> None:
    """Lay out a flow or a tree in ranks along the connectors between the shapes.

    Shapes default to the top-level shapes of the page. Each shape goes one rank past the
    shapes pointing to it; parents are centred over their children. With ports=True,
    connectors without ports leave and enter shapes on the sides facing along `direction`,
    which keeps their routes straight.
    """
    if direction not in _DIRECTIONS:
        raise ValueError(f"direction must be one of {sorted(_DIRECTIONS)}")
    nodes = list(page.children() if cells is None else cells)
    if not nodes:
        return
    ids = {c.id: c for c in nodes}
    edges = [e for e in page.edges if e.source_id in ids and e.target_id in ids]
    succ: dict[str, list[str]] = {i: [] for i in ids}
    for edge in edges:
        if edge.source_id != edge.target_id:
            succ[edge.source_id].append(edge.target_id)

    # Break cycles: drop connectors that point back to a shape still on the DFS stack.
    state: dict[str, int] = {}
    forward: dict[str, list[str]] = {i: [] for i in ids}

    def visit(start: str) -> None:
        stack = [(start, iter(succ[start]))]
        state[start] = 1
        while stack:
            node, children = stack[-1]
            nxt = next(children, None)
            if nxt is None:
                state[node] = 2
                stack.pop()
            elif state.get(nxt) == 1:
                continue
            else:
                if nxt not in forward[node]:
                    forward[node].append(nxt)
                if nxt not in state:
                    state[nxt] = 1
                    stack.append((nxt, iter(succ[nxt])))

    for node in ids:
        if node not in state:
            visit(node)

    pred: dict[str, list[str]] = {i: [] for i in ids}
    for node, targets in forward.items():
        for target in targets:
            pred[target].append(node)

    # Longest-path ranking.
    rank: dict[str, int] = {}
    pending = [n for n in ids if not pred[n]]
    indegree = {n: len(pred[n]) for n in ids}
    order = []
    while pending:
        node = pending.pop(0)
        order.append(node)
        rank[node] = max((rank[p] + 1 for p in pred[node]), default=0)
        for target in forward[node]:
            indegree[target] -= 1
            if indegree[target] == 0:
                pending.append(target)
    ranks: list[list[str]] = []
    for node in order:
        while len(ranks) <= rank[node]:
            ranks.append([])
        ranks[rank[node]].append(node)

    # Order within ranks: a few barycentre sweeps.
    def sweep(layers, neighbours) -> None:
        for i in range(1, len(layers)):
            above = {n: k for k, n in enumerate(layers[i - 1])}
            keyed = []
            for k, node in enumerate(layers[i]):
                linked = [above[n] for n in neighbours[node] if n in above]
                keyed.append((sum(linked) / len(linked) if linked else k, k, node))
            layers[i] = [n for _, _, n in sorted(keyed)]

    for _ in range(4):
        sweep(ranks, pred)
        reversed_ranks = ranks[::-1]
        sweep(reversed_ranks, forward)
        ranks = reversed_ranks[::-1]

    vertical = direction in ("down", "up")

    def along(c: Cell) -> float:  # size along the rank
        return c.width if vertical else c.height

    def across(c: Cell) -> float:  # size between ranks
        return c.height if vertical else c.width

    centre: dict[str, float] = {}

    def place(layer: list[str], wanted: dict[str, float]) -> None:
        cursor = None
        for node in layer:
            size = along(ids[node])
            start = wanted.get(node, centre.get(node, 0.0)) - size / 2
            if cursor is not None:
                start = max(start, cursor + gap)
            centre[node] = start + size / 2
            cursor = start + size

    for layer in ranks:
        place(layer, {})
    for i in range(1, len(ranks)):
        wanted = {n: sum(centre[p] for p in pred[n]) / len(pred[n]) for n in ranks[i] if pred[n]}
        place(ranks[i], wanted)
    for i in range(len(ranks) - 2, -1, -1):
        wanted = {
            n: sum(centre[c] for c in forward[n]) / len(forward[n]) for n in ranks[i] if forward[n]
        }
        place(ranks[i], wanted)

    low = min(centre[n] - along(ids[n]) / 2 for n in ids)
    depth = []
    position = 0.0
    for layer in ranks:
        depth.append(position)
        position += max(across(ids[n]) for n in layer) + rank_gap
    total = position - rank_gap
    for i, layer in enumerate(ranks):
        thickness = max(across(ids[n]) for n in layer)
        for node in layer:
            cell = ids[node]
            a = centre[node] - along(cell) / 2 - low
            b = depth[i] + (thickness - across(cell)) / 2
            if direction in ("up", "left"):
                b = total - b - across(cell)
            if vertical:
                cell.move(x + a, y + b)
            else:
                cell.move(x + b, y + a)

    if ports:
        # Connectors leave and enter on the sides facing along `direction`; several
        # connectors on one side are spread out in the order of the shapes they reach.
        out_side, in_side = {
            "down": ("bottom", "top"),
            "up": ("top", "bottom"),
            "right": ("right", "left"),
            "left": ("left", "right"),
        }[direction]
        laid = [
            e
            for e in edges
            if e.target_id in forward.get(e.source_id, [])
            and not any(k in e.style for k in ("exitX", "exitY", "entryX", "entryY"))
        ]

        def spread(side: str, key) -> dict[str, float]:
            groups: dict[str, list] = {}
            for e in laid:
                groups.setdefault(key(e)[0], []).append(e)
            share = {}
            for group in groups.values():
                group.sort(key=lambda e: centre[key(e)[1]])
                for i, e in enumerate(group):
                    share[e.id] = (i + 1) / (len(group) + 1)
            return share

        exits = spread(out_side, lambda e: (e.source_id, e.target_id))
        entries = spread(in_side, lambda e: (e.target_id, e.source_id))

        def port(side: str, along: float) -> tuple[float, float]:
            return {
                "bottom": (along, 1),
                "top": (along, 0),
                "right": (1, along),
                "left": (0, along),
            }[side]

        for edge in laid:
            exit_x, exit_y = port(out_side, round(exits[edge.id], 3))
            entry_x, entry_y = port(in_side, round(entries[edge.id], 3))
            edge.set_style(exitX=exit_x, exitY=exit_y, entryX=entry_x, entryY=entry_y)
