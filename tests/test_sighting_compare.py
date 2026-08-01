import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.data.sighting_compare import compare_sighting
from antismurf.storage.sightings import PlayerSightingEntry


def _entry(**overrides) -> PlayerSightingEntry:
    base = dict(
        handle="5-S2-1-1000",
        display_name="Nick",
        team_name="Team",
        slot_index=1,
        tier="medium",
        score=25.0,
        triggered_rules=[],
        remark="",
        mmr=1500.0,
        mmr_playlike=2100.0,
        survivor_mmr="-",
        survivor_pl="-",
        kerrigan_mmr="-",
        kerrigan_pl="-",
        core_gap="-",
        snapshot={
            "mmr": 1500,
            "mmr_playlike": 2100,
            "survivor_core": 1400,
            "kerrigan_core": 1600,
            "score": 25,
        },
        first_seen_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        last_seen_at=datetime(2026, 6, 2, tzinfo=timezone.utc),
        seen_count=2,
    )
    base.update(overrides)
    return PlayerSightingEntry(**base)


def test_compare_sighting_shows_mmr_delta() -> None:
    entry = _entry()
    current = {
        "mmr": 1620,
        "mmr_playlike": 2200,
        "survivor_core": 1500,
        "kerrigan_core": 1600,
        "score": 30,
    }
    result = compare_sighting(entry, current)
    assert result.fetch_error is None
    assert "汇总MMR" in result.summary
    assert "120" in result.summary or "+120" in result.summary


def test_compare_sighting_handles_fetch_error() -> None:
    entry = _entry()
    result = compare_sighting(entry, None, fetch_error="timeout")
    assert "无法对比" in result.summary
    assert result.fetch_error == "timeout"


def test_compare_sighting_no_data() -> None:
    entry = _entry(snapshot={})
    result = compare_sighting(entry, {})
    assert "无可对比" in result.summary or result.metric_deltas == []
