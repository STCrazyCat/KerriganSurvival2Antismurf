import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.models.rating_profile import CoreMmrPair, PlaylikeGame, PlayerRatingProfile
from antismurf.scoring.same_match_detector import detect_kerrigan_same_match_spikes


def _profile(handle: str, core: float, games: list[dict]) -> PlayerRatingProfile:
    p = PlayerRatingProfile(
        handle=handle,
        core_mmr=CoreMmrPair(kerrigan=core, survivor=core),
    )
    p.playlike_games = [PlaylikeGame(**g) for g in games]
    return p


def test_same_minute_matches_ignoring_seconds() -> None:
    host = _profile(
        "5-S2-1-1", 2000,
        [{"role": "Kerrigan", "team": 1, "played_like": 2300, "date": "2026-07-20 12:00:00"}],
    )
    player = _profile(
        "5-S2-1-2", 2000,
        [{"role": "Kerrigan", "team": 1, "played_like": 2800, "date": "2026-07-20 12:00:45", "inferred_core": 2600}],
    )
    hits = detect_kerrigan_same_match_spikes(player, host)
    assert len(hits) == 1
    assert hits[0].lift >= 400


def test_cross_minute_not_detected() -> None:
    host = _profile(
        "5-S2-1-1", 2000,
        [{"role": "Kerrigan", "team": 1, "played_like": 2300, "date": "2026-07-20 12:00:00"}],
    )
    player = _profile(
        "5-S2-1-2", 2000,
        [{"role": "Kerrigan", "team": 1, "played_like": 2800, "date": "2026-07-20 12:01:00", "inferred_core": 2600}],
    )
    assert detect_kerrigan_same_match_spikes(player, host) == []


def test_minute_precision_format() -> None:
    host = _profile(
        "5-S2-1-1", 2000,
        [{"role": "Kerrigan", "team": 1, "played_like": 2300, "date": "2026-07-20 12:00"}],
    )
    player = _profile(
        "5-S2-1-2", 2000,
        [{"role": "Kerrigan", "team": 1, "played_like": 2800, "date": "2026-07-20 12:00", "inferred_core": 2600}],
    )
    hits = detect_kerrigan_same_match_spikes(player, host)
    assert len(hits) == 1


def test_role_based_side_without_side_field() -> None:
    """阵营由角色名单判定(role_taxonomy),不依赖 game.side 字段。"""
    host = _profile(
        "5-S2-1-1", 2000,
        [{"role": "Dehaka", "team": 1, "played_like": 2300, "date": "2026-07-20 12:00:00"}],
    )
    player = _profile(
        "5-S2-1-2", 2000,
        [{"role": "Zagara", "team": 1, "played_like": 2800, "date": "2026-07-20 12:00:00", "inferred_core": 2600}],
    )
    hits = detect_kerrigan_same_match_spikes(player, host)
    assert len(hits) == 1


def test_survivor_role_ignored() -> None:
    host = _profile(
        "5-S2-1-1", 2000,
        [{"role": "Technician", "team": 0, "played_like": 2300, "date": "2026-07-20 12:00:00"}],
    )
    player = _profile(
        "5-S2-1-2", 2000,
        [{"role": "Technician", "team": 0, "played_like": 2800, "date": "2026-07-20 12:00:00", "inferred_core": 2600}],
    )
    assert detect_kerrigan_same_match_spikes(player, host) == []


def test_below_threshold_not_detected() -> None:
    host = _profile(
        "5-S2-1-1", 2000,
        [{"role": "Kerrigan", "team": 1, "played_like": 2300, "date": "2026-07-20 12:00:00"}],
    )
    player = _profile(
        "5-S2-1-2", 2000,
        [{"role": "Kerrigan", "team": 1, "played_like": 2200, "date": "2026-07-20 12:00:00", "inferred_core": 2200}],
    )
    assert detect_kerrigan_same_match_spikes(player, host) == []


def test_no_host_games_returns_empty() -> None:
    host = _profile("5-S2-1-1", 2000, [])
    player = _profile(
        "5-S2-1-2", 2000,
        [{"role": "Kerrigan", "team": 1, "played_like": 2800, "date": "2026-07-20 12:00:00", "inferred_core": 2600}],
    )
    assert detect_kerrigan_same_match_spikes(player, host) == []


def test_played_like_fallback_when_inferred_missing() -> None:
    host = _profile(
        "5-S2-1-1", 2000,
        [{"role": "Kerrigan", "team": 1, "played_like": 2300, "date": "2026-07-20 12:00:00"}],
    )
    player = _profile(
        "5-S2-1-2", 2000,
        [{"role": "Kerrigan", "team": 1, "played_like": 2800, "date": "2026-07-20 12:00:00"}],
    )
    hits = detect_kerrigan_same_match_spikes(player, host)
    assert len(hits) == 1
