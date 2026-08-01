"""AntiSmurf — KS2 lobby anti-smurf tool."""

from __future__ import annotations

from pathlib import Path


def _read_version() -> str:
    root = Path(__file__).resolve().parents[2]
    version_file = root / "VERSION"
    if version_file.exists():
        return version_file.read_text(encoding="utf-8").strip()
    return "0.0.0"


__version__ = _read_version()
