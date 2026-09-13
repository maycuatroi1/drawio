"""Offline utilities for editable draw.io files."""

import argparse
import json
import sys
from pathlib import Path

from drawio.document import Document


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate and inspect native draw.io XML")
    version = Path(__file__).with_name("VERSION").read_text(encoding="utf-8").strip()
    parser.add_argument("--version", action="version", version=version)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="Check IDs, references and parent hierarchy")
    validate.add_argument("input", type=Path)
    validate.add_argument(
        "--check-bounds", action="store_true", help="Also reject children outside containers"
    )
    info = commands.add_parser("info", help="Print page IDs, names and cell counts as JSON")
    info.add_argument("input", type=Path)
    url = commands.add_parser("url", help="Encode file contents in an editor URL (no upload)")
    url.add_argument("input", type=Path)
    new = commands.add_parser("new", help="Create an empty one-page document")
    new.add_argument("output", type=Path)
    new.add_argument("--name", default="Overview")
    new.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "new":
            document = Document()
            document.add_page(args.name)
            print(document.save(args.output, overwrite=args.overwrite))
            return 0
        document = Document.load(args.input)
        if args.command == "validate":
            document.validate(check_bounds=args.check_bounds)
            print(f"Valid: {len(document.pages)} page(s)")
        elif args.command == "info":
            print(
                json.dumps(
                    [
                        {
                            "id": page.id,
                            "name": page.name,
                            "shapes": sum(c.element.get("vertex") == "1" for c in page.cells),
                            "connectors": sum(c.element.get("edge") == "1" for c in page.cells),
                        }
                        for page in document.pages
                    ],
                    indent=2,
                )
            )
        elif args.command == "url":
            print(document.to_url())
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print(f"drawio: {exc}", file=sys.stderr)
        return 1
