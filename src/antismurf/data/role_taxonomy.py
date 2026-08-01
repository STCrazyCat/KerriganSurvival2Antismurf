from __future__ import annotations

import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from antismurf.config.settings import _bundled_config_root, _project_root

Side = Literal["kerrigan", "survivor"]
Archetype = Literal["hunter", "defender", "builder", "support"]


@dataclass(frozen=True)
class RoleTaxonomyEntry:
    name: str
    side: Side
    archetype: Archetype
    aliases: tuple[str, ...] = ()


def _taxonomy_path() -> Path:
    root = _project_root()
    bundled = _bundled_config_root()
    for base in (root, bundled):
        path = base / "config" / "role_taxonomy.toml"
        if path.exists():
            return path
    return root / "config" / "role_taxonomy.toml"


@lru_cache(maxsize=1)
def load_role_taxonomy() -> dict[str, RoleTaxonomyEntry]:
    path = _taxonomy_path()
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        data = tomllib.load(f)
    entries: dict[str, RoleTaxonomyEntry] = {}
    for item in data.get("roles", []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        side = str(item.get("side", "survivor"))
        archetype = str(item.get("archetype", "builder"))
        if side not in ("kerrigan", "survivor"):
            continue
        if archetype not in ("hunter", "defender", "builder", "support"):
            continue
        entry = RoleTaxonomyEntry(
            name=name,
            side=side,  # type: ignore[arg-type]
            archetype=archetype,  # type: ignore[arg-type]
            aliases=tuple(str(a) for a in item.get("aliases", [])),
        )
        entries[name.lower()] = entry
        entries[_normalize_role_key(name)] = entry
        for alias in entry.aliases:
            entries[_normalize_role_key(alias)] = entry
    return entries


def _normalize_role_key(name: str) -> str:
    return name.strip().replace(" ", "_").lower()


def resolve_role(
    role_name: str,
    *,
    team_name: str = "",
    team: int | None = None,
) -> RoleTaxonomyEntry | None:
    taxonomy = load_role_taxonomy()
    key = _normalize_role_key(role_name)
    if key in taxonomy:
        return taxonomy[key]
    if role_name.lower() in taxonomy:
        return taxonomy[role_name.lower()]

    side: Side | None = None
    if team_name:
        if "凯瑞甘" in team_name or "kerrigan" in team_name.lower():
            side = "kerrigan"
        elif "幸存" in team_name or "survivor" in team_name.lower():
            side = "survivor"
    if side is None and team is not None:
        side = "kerrigan" if team == 1 else "survivor"

    if side is None:
        return None
    return RoleTaxonomyEntry(
        name=role_name,
        side=side,
        archetype="builder" if side == "survivor" else "hunter",
    )


def clear_taxonomy_cache() -> None:
    load_role_taxonomy.cache_clear()
