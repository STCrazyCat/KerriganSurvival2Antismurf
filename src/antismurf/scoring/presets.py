from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from antismurf.config.settings import _bundled_config_root, _project_root


def list_preset_names() -> list[str]:
    presets_dir = _presets_dir()
    if not presets_dir.exists():
        return ["balanced"]
    names = sorted(p.stem for p in presets_dir.glob("*.toml"))
    return names or ["balanced"]


def load_preset_rules(name: str) -> list[dict[str, Any]]:
    path = _presets_dir() / f"{name}.toml"
    if not path.exists():
        path = _bundled_config_root() / "config" / "scoring_presets" / f"{name}.toml"
    if not path.exists():
        return []
    with open(path, "rb") as f:
        data = tomllib.load(f)
    rules = data.get("expression_rules", [])
    return [r for r in rules if isinstance(r, dict)]


def _presets_dir() -> Path:
    root = _project_root()
    user_dir = root / "config" / "scoring_presets"
    if user_dir.exists():
        return user_dir
    return _bundled_config_root() / "config" / "scoring_presets"
