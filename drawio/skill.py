"""The agent skill that ships inside the package, and its installer."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

NAME = "drawio"
_HOMES = {"claude": ".claude", "codex": ".codex", "agents": ".agents"}


def skill_dir() -> Path:
    return Path(__file__).with_name("skill")


def targets(agent: str, dest: Optional[str] = None) -> list[Path]:
    if dest:
        return [Path(dest).expanduser() / NAME]
    home = Path.home()
    if agent != "all":
        return [home / _HOMES[agent] / "skills" / NAME]
    # Install for the agents this machine has; ~/.agents/skills is the shared default.
    found = [home / d / "skills" / NAME for d in _HOMES.values() if (home / d).is_dir()]
    return found or [home / ".agents" / "skills" / NAME]


def install(agent: str = "all", *, dest: Optional[str] = None, force: bool = False) -> list[Path]:
    """Copy the skill folder; refuses to replace an existing copy unless force=True."""
    source = skill_dir()
    written = []
    for target in targets(agent, dest):
        if target.exists():
            if not force:
                raise FileExistsError(f"{target} exists; pass --force to replace it")
            shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__"))
        written.append(target)
    return written
