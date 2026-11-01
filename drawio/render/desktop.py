"""Export through the draw.io desktop app's command line, when it is installed.

Install draw.io desktop from https://github.com/jgraph/drawio-desktop/releases (all
systems), or with a package manager: `brew install --cask drawio`, `winget install
JGraph.Draw`, `snap install drawio`, or the .deb/.rpm/AppImage. Set DRAWIO_DESKTOP to the
executable if it lives somewhere else.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path
from typing import Optional

_CANDIDATES = {
    "darwin": [
        "/Applications/draw.io.app/Contents/MacOS/draw.io",
        "~/Applications/draw.io.app/Contents/MacOS/draw.io",
    ],
    "win32": [
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "draw.io", "draw.io.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "draw.io", "draw.io.exe"),
    ],
    "linux": [
        "/opt/drawio/drawio",
        "/usr/bin/drawio",
        "/snap/bin/drawio",
        "/var/lib/flatpak/exports/bin/com.jgraph.drawio.desktop",
    ],
}


def _is_ours(path: str) -> bool:
    """Whether `path` is the `drawio` command of a Python package rather than draw.io desktop.

    pip installs that command as a script with a Python shebang on Linux and macOS, and as
    an .exe launcher with the script appended (uncompressed) on Windows. Anything inside a
    Python scripts directory counts as ours too.
    """
    resolved = Path(path).resolve()
    scripts = {sysconfig.get_path("scripts"), str(Path(sys.executable).parent)}
    if any(d and Path(d).resolve() == resolved.parent for d in scripts):
        return True
    try:
        with open(resolved, "rb") as stream:
            head = stream.read(256)
            stream.seek(0, os.SEEK_END)
            stream.seek(max(0, stream.tell() - 65536))
            tail = stream.read()
    except OSError:
        return False
    if head.startswith(b"#!") and b"python" in head.lower():
        return True
    return b"drawio.__main__" in tail or b"from drawio" in tail


def find() -> Optional[str]:
    """Path of the draw.io desktop executable, or None."""
    env = os.environ.get("DRAWIO_DESKTOP")
    if env:
        return env if Path(env).expanduser().exists() else None
    platform = "win32" if sys.platform.startswith("win") else sys.platform
    for candidate in _CANDIDATES.get(platform, _CANDIDATES["linux"]):
        path = Path(candidate).expanduser()
        if path.is_file():
            return str(path)
    for name in ("drawio", "draw.io"):
        found = shutil.which(name)
        if found and not _is_ours(found):
            return found
    return None


def export(
    source: Path,
    output: Path,
    *,
    fmt: str,
    page: int = 0,
    scale: float = 1,
    border: int = 10,
    transparent: bool = False,
    all_pages: bool = False,
    executable: Optional[str] = None,
    timeout: float = 120,
) -> None:
    exe = executable or find()
    if not exe:
        raise RuntimeError("draw.io desktop was not found; see `drawio doctor`.")
    command = [exe, "--export", "--format", fmt, "--output", str(output)]
    command += ["--border", str(border), "--scale", f"{scale:g}"]
    if fmt == "pdf":
        command += ["--crop"]
        if all_pages:
            command += ["--all-pages"]
    if not (fmt == "pdf" and all_pages):
        command += ["--page-index", str(page + 1)]
    if transparent and fmt == "png":
        command += ["--transparent"]
    command.append(str(source))
    if sys.platform.startswith("linux"):
        command.insert(1, "--no-sandbox")
        command.insert(2, "--disable-gpu")
        if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            if shutil.which("xvfb-run"):
                command = ["xvfb-run", "-a", *command]
            else:
                raise RuntimeError(
                    "draw.io desktop needs a display on Linux; install xvfb (xvfb-run) or use"
                    " --backend native."
                )
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0 or not output.exists():
        message = (result.stderr or result.stdout).strip().splitlines()[-3:]
        raise RuntimeError("draw.io desktop export failed: " + " | ".join(message))
