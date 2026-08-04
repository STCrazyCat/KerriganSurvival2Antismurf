"""Same-match Kerrigan MMR spike detection (screen-watcher / smurf signal).

A "same-match spike" is a playlike game where the player:
- played a Kerrigan-side hero (Kerrigan, Zagara, Dehaka, Thakras, Niadra,
  Brakk, Glevig, Phaegore, Izsha, Malus, Kraith, Sir Roachington), and
- showed an anomalous MMR jump (inferred core >= threshold above their
  Kerrigan core MMR — same semantics as the existing spike detection), and
- played within the same minute as a game the host (room owner) was in
  (i.e. they were in the same match as the host).

Timestamps are compared at minute precision: seconds (if present) are
ignored, so a game counts as the same match when its minute equals a host
game's minute.

Each hit contributes a fixed suspicion bonus (see stage1_engine).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from antismurf.data.role_taxonomy import resolve_role
from antismurf.models.rating_profile import PlayerRatingProfile


@dataclass
class SameMatchSpike:
    game_date: str
    role: str
    side: str
    inferred_core: float
    kerrigan_core: float
    lift: float


def _parse_game_date(value: str) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _to_minute(dt: datetime) -> datetime:
    return dt.replace(second=0, microsecond=0)


def detect_kerrigan_same_match_spikes(
    player_profile: PlayerRatingProfile,
    host_profile: PlayerRatingProfile,
    *,
    threshold: float = 400.0,
) -> list[SameMatchSpike]:
    """Return the player's Kerrigan games that spike and match the host's timeline.

    Match rule: minute precision — a player game matches when its
    (minute-truncated) timestamp equals a host game's (minute-truncated)
    timestamp. Kerrigan side is decided by the role taxonomy, falling back
    to the game's own `side` field.

    Uses `inferred_core` (played_like minus class offset) when available,
    falling back to raw `played_like` — same semantics as profile_builder's
    spike detection.
    """
    host_minutes: list[datetime] = []
    for game in host_profile.playlike_games:
        dt = _parse_game_date(game.date)
        if dt is not None:
            host_minutes.append(_to_minute(dt))

    hits: list[SameMatchSpike] = []
    core = player_profile.core_mmr.kerrigan
    if core is None:
        return hits

    for game in player_profile.playlike_games:
        tax = resolve_role(game.role, team=game.team)
        side = game.side or (tax.side if tax else None)
        if side != "kerrigan":
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
        if _to_minute(dt) not in host_minutes:
            continue
        hits.append(
            SameMatchSpike(
                game_date=game.date,
                role=game.role,
                side="kerrigan",
                inferred_core=round(value, 1),
                kerrigan_core=round(core, 1),
                lift=round(lift, 1),
            )
        )
    return hits
