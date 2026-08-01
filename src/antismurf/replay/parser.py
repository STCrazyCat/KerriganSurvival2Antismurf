"""Minimal SC2 replay parsing for KS2 upload filtering."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from antismurf.config.settings import AppConfig

logger = logging.getLogger(__name__)

DEFAULT_KS2_MAP_PREFIXES = ("凯瑞甘生存2", "Kerrigan Survival", "凯瑞甘生存")


def _load_replay(path: Path) -> Any:
    import sc2reader

    return sc2reader.load_replay(str(path), load_map=True)


def is_ks2_replay_map_name(
    map_name: str,
    prefixes: tuple[str, ...] | list[str] | None = None,
) -> bool:
    normalized = map_name.strip()
    if not normalized:
        return False
    tokens = prefixes or DEFAULT_KS2_MAP_PREFIXES
    for prefix in tokens:
        token = prefix.strip()
        if not token:
            continue
        if normalized.startswith(token) or token in normalized:
            return True
    if "英雄" in normalized and "★" in normalized:
        return True
    return False


def parse_replay_file(
    path: Path | str,
    config: AppConfig,
    *,
    ks2_only: bool = True,
) -> list[Any]:
    replay_path = Path(path)
    try:
        replay = _load_replay(replay_path)
    except Exception as exc:
        logger.debug("Replay parse failed for %s: %s", replay_path, exc)
        return []

    map_name = getattr(replay, "map_name", "") or ""
    if ks2_only and not is_ks2_replay_map_name(
        map_name,
        config.replays_map_prefixes,
    ):
        return []
    return [replay]
