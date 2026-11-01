"""Offline utilities for editable draw.io files.

Every command that reports something accepts --json, so an agent can read the result
without parsing prose. Exit status: 0 success, 1 failure or findings, 2 bad usage.
"""

import argparse
import json
import sys
from pathlib import Path

from drawio.document import Document

_VERSION = Path(__file__).with_name("VERSION").read_text(encoding="utf-8").strip()


def _emit(data, as_json: bool, text: str) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False) if as_json else text)


def _pages_info(document):
    return [
        {
            "id": page.id,
            "name": page.name,
            "shapes": sum(c.element.get("vertex") == "1" for c in page.cells),
            "connectors": sum(c.element.get("edge") == "1" for c in page.cells),
        }
        for page in document.pages
    ]


def _cmd_new(args):
    document = Document()
    document.add_page(args.name)
    print(document.save(args.output, overwrite=args.overwrite))
    return 0


def _cmd_validate(args):
    document = Document.load(args.input)
    document.validate(check_bounds=args.check_bounds)
    _emit(
        {"valid": True, "pages": len(document.pages)},
        args.json,
        f"Valid: {len(document.pages)} page(s)",
    )
    return 0


def _cmd_info(args):
    print(json.dumps(_pages_info(Document.load(args.input)), indent=2, ensure_ascii=False))
    return 0


def _cmd_url(args):
    print(Document.load(args.input).to_url())
    return 0


def _cmd_render(args):
    from drawio.render import render, render_all

    source = Path(args.input)
    options = dict(
        scale=args.scale,
        border=args.border,
        backend=args.backend,
        aspect=args.aspect,
        transparent=args.transparent,
        download=not args.offline,
    )
    if args.all_pages:
        fmt = (args.format or "png").lower()
        folder = Path(args.output) if args.output else source.with_suffix("")
        results = render_all(source, folder, fmt=fmt, **options)
    else:
        output = args.output or str(source.with_suffix("." + (args.format or "png").lower()))
        results = [render(source, output, page=args.page, fmt=args.format, **options)]
    data = [
        {"output": str(r.path), "backend": r.backend, "page": r.page, "notes": r.notes}
        for r in results
    ]
    lines = []
    for r in results:
        lines.append(f"{r.path} (page {r.page}, {r.backend} backend)")
        lines += [f"  note: {n}" for n in r.notes]
    _emit(data, args.json, "\n".join(lines))
    return 0


def _cmd_lint(args):
    from drawio.lint import SEVERITIES, check, parse_fit

    document = Document.load(args.input)
    document.validate()
    fit = parse_fit(args.fit, args.min_pt) if args.fit else None
    issues = check(document, fit=fit, pages=args.page or None)
    threshold = SEVERITIES.index(args.fail_on)
    failing = [i for i in issues if SEVERITIES.index(i.severity) <= threshold]
    counts = {s: sum(i.severity == s for i in issues) for s in SEVERITIES}
    if args.json:
        print(
            json.dumps(
                {"file": args.input, "summary": counts, "issues": [i.to_dict() for i in issues]},
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        for issue in issues:
            print(f"{issue.severity}: [{issue.code}] page {issue.page}: {issue.message}")
            if issue.hint:
                print(f"    fix: {issue.hint}")
        summary = ", ".join(f"{n} {s}(s)" for s, n in counts.items() if n)
        print(f"{args.input}: {summary or 'no layout problems found'}")
    return 1 if failing else 0


def _cmd_inspect(args):
    from drawio.scene import build

    document = Document.load(args.input)
    pages = []
    for page in document.pages:
        if args.page and args.page not in (page.id, page.name):
            continue
        scene = build(page)
        shapes = [
            {
                "id": s.id,
                "label": s.label.text if s.label else "",
                "kind": s.kind,
                "box": [round(v, 1) for v in s.box],
                "parent": s.parent if s.parent not in ("0", "1") else None,
                "container": s.container,
            }
            for s in scene.shapes
        ]
        connectors = [
            {
                "id": e.id,
                "source": e.source,
                "target": e.target,
                "label": " / ".join(label.text for label in e.labels),
                "route": [[round(x, 1), round(y, 1)] for x, y in e.points],
            }
            for e in scene.connectors
        ]
        bounds = [round(v, 1) for v in scene.bounds()]
        pages.append(
            {
                "id": page.id,
                "name": page.name,
                "bounds": bounds,
                "shapes": shapes,
                "connectors": connectors,
            }
        )
    if args.json:
        print(json.dumps(pages, indent=2, ensure_ascii=False))
        return 0
    for page in pages:
        print(f"page {page['id']} {page['name']!r}  bounds x,y,w,h={page['bounds']}")
        for s in page["shapes"]:
            parent = f" in {s['parent']}" if s["parent"] else ""
            label = " ".join(s["label"].split())
            print(f"  shape {s['id']:<12} {s['kind']:<10} {s['box']}{parent}  {label[:60]!r}")
        for e in page["connectors"]:
            label = f"  {e['label']!r}" if e["label"] else ""
            print(f"  edge  {e['id']:<12} {e['source']} -> {e['target']}{label}")
    return 0


def _write(document, args) -> Path:
    target = args.output or args.input
    return document.save(target, overwrite=args.output is None or args.overwrite)


def _cmd_fit(args):
    document = Document.load(args.input)
    resized = []
    for page in document.pages:
        if args.autosize:
            from drawio.lint import check_scene
            from drawio.scene import build

            for issue in check_scene(build(page)):
                if issue.code == "text-overflow":
                    page.autosize(issue.cells[0], max_width=args.max_width)
                    resized.append(issue.cells[0])
        page.fit(padding=args.padding)
    path = _write(document, args)
    _emit({"output": str(path), "autosized": resized}, args.json, f"{path}")
    return 0


def _cmd_layout(args):
    from drawio.layout import layered

    document = Document.load(args.input)
    pages = [p for p in document.pages if not args.page or args.page in (p.id, p.name)]
    if not pages:
        raise ValueError(f"No page with ID or name {args.page!r}")
    for page in pages:
        layered(page, direction=args.direction, rank_gap=args.rank_gap, gap=args.gap)
        page.fit()
    path = _write(document, args)
    _emit({"output": str(path), "pages": [p.id for p in pages]}, args.json, f"{path}")
    return 0


def _cmd_merge(args):
    merged = Document()
    for name in args.inputs:
        for page in Document.load(name).pages:
            merged.import_page(page)
    path = merged.save(args.output, overwrite=args.overwrite)
    _emit({"output": str(path), "pages": _pages_info(merged)}, args.json, f"{path}")
    return 0


def _cmd_shapes(args):
    from drawio.shapes import ARROWS, PALETTE, SHAPES

    data = {"shapes": SHAPES, "colors": PALETTE, "arrows": list(ARROWS)}
    text = [
        "shapes (page.box(..., shape=NAME)): " + ", ".join(SHAPES),
        "colors (style=drawio.shapes.color(NAME)): " + ", ".join(PALETTE),
        "arrows (page.connect(..., arrow=NAME)): " + ", ".join(ARROWS),
    ]
    _emit(data, args.json, "\n".join(text))
    return 0


def _cmd_doctor(args):
    from drawio.doctor import diagnose

    report = diagnose()
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0
    for item in report["checks"]:
        mark = "ok " if item["ok"] else "-- "
        print(f"{mark} {item['name']}: {item['detail']}")
        if not item["ok"] and item.get("fix"):
            print(f"     fix: {item['fix']}")
    print("render backends available: " + ", ".join(report["backends"]))
    return 0


def _cmd_skill(args):
    from drawio.skill import install, skill_dir

    if args.action == "path":
        print(skill_dir())
        return 0
    if args.action == "show":
        print((skill_dir() / "SKILL.md").read_text(encoding="utf-8"))
        return 0
    written = install(args.agent, dest=args.dest, force=args.force)
    _emit([str(p) for p in written], args.json, "\n".join(f"installed {p}" for p in written))
    return 0


def _parser():
    parser = argparse.ArgumentParser(
        prog="drawio",
        description="Build, check and export editable draw.io diagrams. "
        "Run `drawio skill show` for the agent workflow.",
    )
    parser.add_argument("--version", action="version", version=_VERSION)
    commands = parser.add_subparsers(dest="command", required=True)

    def add(name, func, help):
        sub = commands.add_parser(name, help=help, description=help)
        sub.set_defaults(func=func)
        return sub

    def json_flag(sub):
        sub.add_argument("--json", action="store_true", help="Print machine-readable JSON")

    def output_flags(sub):
        sub.add_argument("-o", "--output", help="Write here instead of updating the input")
        sub.add_argument("--overwrite", action="store_true", help="Replace an existing output")

    new = add("new", _cmd_new, "Create an empty one-page document")
    new.add_argument("output", type=Path)
    new.add_argument("--name", default="Overview")
    new.add_argument("--overwrite", action="store_true")

    validate = add("validate", _cmd_validate, "Check IDs, references and parent hierarchy")
    validate.add_argument("input", type=Path)
    validate.add_argument(
        "--check-bounds", action="store_true", help="Also reject children outside containers"
    )
    json_flag(validate)

    info = add("info", _cmd_info, "Print page IDs, names and cell counts as JSON")
    info.add_argument("input", type=Path)

    url = add("url", _cmd_url, "Encode file contents in an editor URL (no upload)")
    url.add_argument("input", type=Path)

    render = add("render", _cmd_render, "Export a page to PNG, SVG, PDF or JPEG")
    render.add_argument("input")
    render.add_argument("-o", "--output", help="Output file (or folder with --all-pages)")
    render.add_argument("-f", "--format", choices=["png", "svg", "pdf", "jpg", "jpeg"])
    render.add_argument("-p", "--page", help="Page index (0-based), ID or name; default first")
    render.add_argument("--all-pages", action="store_true", help="One file per page")
    render.add_argument("-s", "--scale", type=float, default=1)
    render.add_argument("--border", type=int, default=10)
    render.add_argument(
        "--backend",
        choices=["auto", "native", "desktop", "browser"],
        default="auto",
        help="auto: draw.io desktop if installed, else native (default)",
    )
    render.add_argument("--aspect", help="Pad the canvas to a ratio such as 16:9 (native)")
    render.add_argument("--transparent", action="store_true", help="No background (PNG)")
    render.add_argument(
        "--offline", action="store_true", help="Never download the diagrams.net viewer"
    )
    json_flag(render)

    lint = add("lint", _cmd_lint, "Find overflowing text, overlaps and crossing connectors")
    lint.add_argument("input")
    lint.add_argument("-p", "--page", action="append", help="Only these page IDs or names")
    lint.add_argument(
        "--fit",
        help="Size the picture will be shown at, e.g. 8.15x4.85in, 16cm, 1200px; reports text"
        " smaller than --min-pt",
    )
    lint.add_argument("--min-pt", type=float, default=12)
    lint.add_argument(
        "--fail-on",
        choices=["error", "warning", "info"],
        default="warning",
        help="Lowest severity that makes the exit status 1 (default warning)",
    )
    json_flag(lint)

    inspect = add("inspect", _cmd_inspect, "List shapes and connectors with page coordinates")
    inspect.add_argument("input")
    inspect.add_argument("-p", "--page", help="Only this page ID or name")
    json_flag(inspect)

    fit = add("fit", _cmd_fit, "Grow containers and the page to fit their contents")
    fit.add_argument("input")
    output_flags(fit)
    fit.add_argument("--padding", type=float, default=20)
    fit.add_argument(
        "--autosize", action="store_true", help="Also grow shapes whose text overflows"
    )
    fit.add_argument("--max-width", type=float, help="Widest a shape may grow with --autosize")
    json_flag(fit)

    layout = add("layout", _cmd_layout, "Arrange top-level shapes in ranks along connectors")
    layout.add_argument("input")
    output_flags(layout)
    layout.add_argument("-p", "--page", help="Only this page ID or name")
    layout.add_argument("--direction", choices=["down", "up", "right", "left"], default="down")
    layout.add_argument("--rank-gap", type=float, default=80)
    layout.add_argument("--gap", type=float, default=40)
    json_flag(layout)

    merge = add("merge", _cmd_merge, "Combine the pages of several files into one")
    merge.add_argument("output")
    merge.add_argument("inputs", nargs="+")
    merge.add_argument("--overwrite", action="store_true")
    json_flag(merge)

    shapes = add("shapes", _cmd_shapes, "List shape names, colour presets and arrow ends")
    json_flag(shapes)

    doctor = add("doctor", _cmd_doctor, "Report which render backends and fonts are available")
    json_flag(doctor)

    skill = add("skill", _cmd_skill, "Install or print the agent skill shipped with drawio")
    skill.add_argument("action", choices=["install", "show", "path"])
    skill.add_argument(
        "--agent",
        choices=["claude", "codex", "agents", "all"],
        default="all",
        help="Where to install: ~/.claude/skills, ~/.codex/skills, ~/.agents/skills",
    )
    skill.add_argument("--dest", help="Install into this skills folder instead")
    skill.add_argument("--force", action="store_true", help="Replace an installed copy")
    json_flag(skill)
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        print(f"drawio: {exc}", file=sys.stderr)
        return 1
