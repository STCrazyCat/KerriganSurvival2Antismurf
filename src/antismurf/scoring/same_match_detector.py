"""Same-match Kerrigan MMR spike detection.

A "same-match spike" is a playlike game where the player:
- played on the Kerrigan side,
- showed an anomalous MMR jump (inferred core >= threshold above their
  Kerrigan core MMR — same semantics as the existing spike detection), and
- played within `window_sec` of a game the host (room owner) was in
  (i.e. they were in the same match as the host).

Each hit contributes a fixed suspicion bonus (see stage1_engine).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from antismurf.models.rating_profile import PlayerRatingProfile


@dataclass
class SameMatchSpike:
    game_date: str
    side: str
    inferred_core: float
    kerrigan_core: float
    lift: float


def _parse_game_date(value: str) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _within_window(dt: datetime, host_times: list[datetime], window_sec: float) -> bool:
    lo = dt - timedelta(seconds=window_sec)
    hi = dt + timedelta(seconds=window_sec)
    return any(lo <= host_dt <= hi for host_dt in host_times)


def detect_kerrigan_same_match_spikes(
    player_profile: PlayerRatingProfile,
    host_profile: PlayerRatingProfile,
    *,
    threshold: float = 400.0,
    window_sec: float = 30.0,
) -> list[SameMatchSpike]:
    """Return the player's Kerrigan games that spike and match the host's timeline.

    Uses `inferred_core` (played_like minus class offset) when available,
    falling back to raw `played_like` — same semantics as profile_builder's
    spike detection.
    """
    host_times: list[datetime] = []
    for game in host_profile.playlike_games:
        dt = _parse_game_date(game.date)
        if dt is not None:
            host_times.append(dt)

    hits: list[SameMatchSpike] = []
    core = player_profile.core_mmr.kerrigan
    if core is None:
        return hits

    for game in player_profile.playlike_games:
        if game.side != "kerrigan":
            continue
        value = game.inferred_core if game.inferred_core is not None else game.played_like
        if value is None:
            continue
        lift = value - core
        if lift < threshold:
            continue
        dt = _parse_game_date(game.date)
        if dt is None:
            continue
        if not _within_window(dt, host_times, window_sec):
            continue
        hits.append(
            SameMatchSpike(
                game_date=game.date,
                side="kerrigan",
                inferred_core=round(value, 1),
                kerrigan_core=round(core, 1),
                lift=round(lift, 1),
            )
        )
    return hits
