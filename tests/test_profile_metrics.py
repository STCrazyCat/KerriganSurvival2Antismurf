import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.data.profile_builder import build_profile_from_ks2_wiki


def test_lift_top3_core_max_and_recent_growth() -> None:
    mmr_data = {
        "cores": {"survivor": 1500, "kerrigan": 1400},
        "roles_survivor": [
            {
                "role_name": "Marine",
                "core_mmr": 1500,
                "class_mmr": 100,
                "mmr": 1600,
                "plays": 12,
            }
        ],
    }
    games = []
    for idx, pl in enumerate([2200, 2250, 2300, 2400, 2500, 2600]):
        games.append(
            {
                "date": f"2026-06-{10 + idx:02d} 12:00:00",
                "role": "Marine",
                "team": 0,
                "played_like": pl + 100,
            }
        )
    profile = build_profile_from_ks2_wiki(
        "5-S2-1-1000",
        mmr_data,
        {"games": games},
    )
    derived = profile.derived
    assert derived.lift_top3_core_max is not None
    assert derived.lift_top3_core_max > 800
    assert derived.playlike_recent_growth is not None
    assert derived.playlike_recent_growth > 0
    assert derived.data_quality.community_match_count == 12
