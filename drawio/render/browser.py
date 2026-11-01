"""Export with the official diagrams.net viewer in a headless browser (Playwright).

This draws every draw.io shape and stencil exactly as the editor does. It needs
`pip install 'drawio-python[browser-render]'` and a Chromium-family browser: Playwright's
own (`playwright install chromium`), or an installed Chrome or Edge, which is tried
automatically when Playwright's is missing. The viewer script (viewer-static.min.js,
Apache-2.0, about 5 MB) is downloaded once into the user cache directory; set
DRAWIO_VIEWER_JS to use a local copy instead, e.g. on machines without network access.
"""

from __future__ import annotations

import html
import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Optional

VIEWER_URL = "https://viewer.diagrams.net/js/viewer-static.min.js"


def cache_dir() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "drawio-python" / "Cache"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "drawio-python"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "drawio-python"


def viewer_script(download: bool = True) -> Optional[Path]:
    """Local path of the viewer script, downloading it on first use when allowed."""
    env = os.environ.get("DRAWIO_VIEWER_JS")
    if env:
        return Path(env).expanduser() if Path(env).expanduser().is_file() else None
    path = cache_dir() / "viewer-static.min.js"
    if path.is_file() and path.stat().st_size > 100_000:
        return path
    if not download:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".part")
    # The CDN rejects urllib's default User-Agent.
    request = urllib.request.Request(VIEWER_URL, headers={"User-Agent": "drawio-python"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            partial.write_bytes(response.read())
    except OSError as exc:
        raise RuntimeError(
            f"Could not download the diagrams.net viewer from {VIEWER_URL}: {exc}. Download it"
            " yourself and set DRAWIO_VIEWER_JS to the file."
        ) from exc
    partial.replace(path)
    return path


def available() -> bool:
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return False
    return True


def _launch(playwright):
    errors = []
    executable = os.environ.get("DRAWIO_CHROME")
    attempts = [{"executable_path": executable}] if executable else []
    attempts += [{}, {"channel": "chrome"}, {"channel": "msedge"}, {"channel": "chromium"}]
    for options in attempts:
        try:
            return playwright.chromium.launch(**options)
        except Exception as exc:  # Playwright raises its own Error type
            errors.append(str(exc).splitlines()[0])
    raise RuntimeError(
        "No usable browser for --backend browser. Run `playwright install chromium`, install"
        " Chrome or Edge, or set DRAWIO_CHROME. Tried: " + "; ".join(errors)
    )


_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{margin:0;padding:0;background:transparent}
</style></head><body><div id="host"><div class="mxgraph" data-mxgraph="{config}"></div></div>
</body></html>"""


def export(
    xml: str,
    output: Path,
    *,
    fmt: str,
    page: int = 0,
    scale: float = 1,
    border: int = 10,
    transparent: bool = False,
    download: bool = True,
    timeout: float = 60,
    size: tuple[float, float] = (1600, 1200),
) -> None:
    if not available():
        raise RuntimeError(
            "--backend browser needs Playwright: pip install 'drawio-python[browser-render]'"
        )
    script = viewer_script(download)
    if script is None:
        raise RuntimeError(
            "The diagrams.net viewer script is not cached and downloading is off; set"
            f" DRAWIO_VIEWER_JS or allow one download from {VIEWER_URL}."
        )
    from playwright.sync_api import sync_playwright

    config = {
        "xml": xml,
        "page": page,
        "border": border,
        "nav": False,
        "toolbar": "",
        "lightbox": False,
        "resize": True,
        "highlight": "none",
    }
    with sync_playwright() as p:
        browser = _launch(p)
        try:
            # The viewport must hold the whole diagram, or the screenshot is cut off.
            margin = 4 * border + 40
            viewport = {"width": int(size[0] + margin), "height": int(size[1] + margin)}
            context = browser.new_context(
                device_scale_factor=scale, color_scheme="light", viewport=viewport
            )
            tab = context.new_page()
            tab.set_default_timeout(timeout * 1000)
            # The viewer renders .mxgraph elements present when its script loads. Adding the
            # element afterwards and calling GraphViewer.processElements() shifts HTML labels.
            attribute = html.escape(json.dumps(config), quote=True)
            tab.set_content(_PAGE.replace("{config}", attribute))
            tab.add_script_tag(path=str(script))
            svg = tab.wait_for_selector("#host svg", state="attached")
            tab.wait_for_timeout(300)
            if not transparent:
                tab.evaluate("document.body.style.background = '#ffffff'")
            if fmt == "svg":
                # HTML labels stay in foreignObject: browsers show them, rsvg-convert and
                # LaTeX do not. The native backend writes plain SVG text instead.
                markup = tab.evaluate(
                    """() => { const s = document.querySelector('#host svg');
                    s.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
                    return new XMLSerializer().serializeToString(s); }"""
                )
                output.write_text('<?xml version="1.0" encoding="UTF-8"?>\n' + markup, "utf-8")
            elif fmt == "pdf":
                box = svg.bounding_box()
                tab.pdf(
                    path=str(output),
                    width=f"{box['width'] + 2:.0f}px",
                    height=f"{box['height'] + 2:.0f}px",
                    print_background=True,
                    page_ranges="1",
                )
            else:
                svg.screenshot(
                    path=str(output),
                    omit_background=transparent,
                    type="jpeg" if fmt == "jpg" else fmt,
                )
        finally:
            browser.close()
