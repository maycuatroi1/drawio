"""What this machine can do with drawio-python, and how to enable what is missing."""

from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import sys
from pathlib import Path

_CHROME = {
    "darwin": [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ],
    "win32": [
        os.path.join(
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            r"Google\Chrome\Application\chrome.exe",
        ),
        os.path.join(
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
            r"Microsoft\Edge\Application\msedge.exe",
        ),
    ],
}


def _has(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def _system_browser():
    env = os.environ.get("DRAWIO_CHROME")
    if env:
        return env
    key = "win32" if sys.platform.startswith("win") else sys.platform
    for path in _CHROME.get(key, []):
        if Path(path).is_file():
            return path
    for name in (
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
        "microsoft-edge",
        "msedge",
        "chrome",
    ):
        found = shutil.which(name)
        if found:
            return found
    return None


def _playwright_chromium():
    if not _has("playwright"):
        return None
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            path = p.chromium.executable_path
        return path if path and Path(path).exists() else None
    except Exception:
        return None


def diagnose() -> dict:
    from . import __file__ as package_file
    from .render import browser, desktop
    from .render.fonts import font_path

    version = Path(package_file).with_name("VERSION").read_text(encoding="utf-8").strip()
    pillow = _has("PIL")
    vector_pdf = _has("cairosvg") or bool(shutil.which("rsvg-convert"))
    desktop_path = desktop.find()
    has_playwright = _has("playwright")
    chromium = _playwright_chromium() if has_playwright else None
    system_browser = _system_browser()
    viewer = browser.viewer_script(download=False)
    font = font_path("Helvetica") if pillow else None
    checks = [
        {
            "name": "drawio-python",
            "ok": True,
            "detail": f"{version} at {Path(package_file).parent} (Python {platform.python_version()})",
        },
        {"name": "native SVG", "ok": True, "detail": "always available, no dependencies"},
        {
            "name": "Pillow (PNG, JPEG, PDF)",
            "ok": pillow,
            "detail": "installed" if pillow else "missing",
            "fix": "pip install 'drawio-python[render]'",
        },
        {
            "name": "vector PDF converter",
            "ok": vector_pdf,
            "detail": "cairosvg or rsvg-convert found"
            if vector_pdf
            else "none; native PDF output is a raster image",
            "fix": "pip install cairosvg, or install librsvg (rsvg-convert)",
        },
        {
            "name": "raster font",
            "ok": bool(font),
            "detail": font or "Pillow's built-in font",
            "fix": "install Arial, Liberation Sans, DejaVu Sans or Noto Sans, or set DRAWIO_FONT",
        },
        {
            "name": "draw.io desktop",
            "ok": bool(desktop_path),
            "detail": desktop_path or "not found",
            "fix": "https://github.com/jgraph/drawio-desktop/releases (or set DRAWIO_DESKTOP)",
        },
        {
            "name": "Playwright",
            "ok": has_playwright,
            "detail": "installed" if has_playwright else "missing",
            "fix": "pip install 'drawio-python[browser-render]'",
        },
        {
            "name": "browser for --backend browser",
            "ok": bool(chromium or system_browser),
            "detail": chromium or system_browser or "none",
            "fix": "playwright install chromium, or install Chrome/Edge, or set DRAWIO_CHROME",
        },
        {
            "name": "diagrams.net viewer script",
            "ok": bool(viewer),
            "detail": str(viewer) if viewer else "not cached; downloaded on first browser render",
            "fix": f"allow one download from {browser.VIEWER_URL} or set DRAWIO_VIEWER_JS",
        },
    ]
    backends = ["native (svg)"]
    if pillow:
        backends.append("native (png, jpg, pdf)")
    if desktop_path:
        backends.append("desktop")
    if has_playwright and (chromium or system_browser):
        backends.append("browser")
    return {"version": version, "checks": checks, "backends": backends}
