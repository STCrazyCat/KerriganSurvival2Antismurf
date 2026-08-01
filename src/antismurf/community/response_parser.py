from __future__ import annotations

from typing import Any


def parse_rating_payload(data: dict[str, Any]) -> tuple[float | None, float | None]:
    """Extract mmr and mmr_playlike from varied API response shapes."""
    sources: list[dict[str, Any]] = [data]
    for key in ("data", "result", "rating", "player"):
        nested = data.get(key)
        if isinstance(nested, dict):
            sources.append(nested)

    mmr = None
    playlike = None
    for src in sources:
        if mmr is None:
            mmr = _float_or_none(
                src.get("mmr", src.get("MMR", src.get("rating")))
            )
        if playlike is None:
            playlike = _float_or_none(
                src.get(
                    "mmr_playlike",
                    src.get("mmrPlaylike", src.get("MMR_playlike")),
                )
            )
    return mmr, playlike


def parse_ks2_wiki_rating(
    mmr_data: dict[str, Any],
    playlike_data: dict[str, Any] | None = None,
) -> tuple[float | None, float | None]:
    """Map KS2 Wiki /api/mmr + /api/played_like to scoring MMR fields."""
    cores = mmr_data.get("cores")
    survivor = None
    kerrigan = None
    if isinstance(cores, dict):
        survivor = _float_or_none(cores.get("survivor"))
        kerrigan = _float_or_none(cores.get("kerrigan"))

    core_values = [v for v in (survivor, kerrigan) if v is not None]
    mmr = min(core_values) if core_values else None

    if mmr is None:
        lb = mmr_data.get("leaderboard_match")
        if isinstance(lb, dict):
            mmr = _float_or_none(lb.get("mmr"))

    playlike = _average_played_like(playlike_data)
    return mmr, playlike


def _average_played_like(data: dict[str, Any] | None) -> float | None:
    if not data:
        return None
    games = data.get("games")
    if not isinstance(games, list):
        return None
    values: list[float] = []
    for game in games:
        if not isinstance(game, dict):
            continue
        value = _float_or_none(game.get("played_like"))
        if value is not None:
            values.append(value)
    if not values:
        return None
    return round(sum(values) / len(values))


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
