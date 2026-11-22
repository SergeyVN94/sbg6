"""Locate bundled assets in the source tree and in frozen builds."""

from __future__ import annotations

import sys
from pathlib import Path


def asset_path(name: str) -> Path:
    bases: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bases.append(Path(meipass))
    bases.append(Path(__file__).resolve().parent.parent)
    bases.append(Path(sys.executable).resolve().parent)
    for base in bases:
        candidate = base / "assets" / name
        if candidate.exists():
            return candidate
    return bases[0] / "assets" / name
