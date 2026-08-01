import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.data.profile_builder import build_profile_from_ks2_wiki
from antismurf.data.role_taxonomy import resolve_role


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


def test_resolve_role_taxonomy():
    entry = resolve_role("Dark_Templar")
    assert entry is not None
    assert entry.side == "survivor"
    assert entry.archetype == "support"

    k = resolve_role("Kerrigan")
    assert k is not None
    assert k.side == "kerrigan"
    assert k.archetype == "hunter"


def test_build_profile_infers_core_playlike():
    mmr_data = {
        "cores": {"survivor": 2573, "kerrigan": 3181},
        "roles_survivor": [
            {
                "role_name": "Dark_Templar",
                "team_name": "幸存者",
                "core_mmr": 2573,
                "class_mmr": 32,
                "mmr": 2605,
            }
        ],
        "roles_kerrigan": [
            {
                "role_name": "Kerrigan",
                "team_name": "凯瑞甘",
                "core_mmr": 3181,
                "class_mmr": 96,
                "mmr": 3277,
            }
        ],
    }
    playlike_data = {
        "games": [
            {"role": "Kerrigan", "team": 1, "played_like": 3000.0},
            {"role": "Dark_Templar", "team": 0, "played_like": 2500.0},
        ]
    }
    profile = build_profile_from_ks2_wiki("5-S2-1-999", mmr_data, playlike_data)
    assert profile.core_mmr.kerrigan == 3181
    assert profile.derived.core_playlike.kerrigan is not None
    assert profile.derived.core_playlike.survivor is not None
    assert profile.derived.lift_core_max is not None


def test_build_profile_detects_playlike_spikes():
    mmr_data = {
        "cores": {"survivor": 1607, "kerrigan": 2099},
        "roles_survivor": [
            {
                "role_name": "Energizer",
                "core_mmr": 1607,
                "class_mmr": 125,
                "mmr": 1732,
            },
            {
                "role_name": "Technician",
                "core_mmr": 1607,
                "class_mmr": 150,
                "mmr": 1757,
            },
        ],
    }
    playlike_data = {
        "games": [
            {"role": "Energizer", "team": 0, "played_like": 2287.0},
            {"role": "Energizer", "team": 0, "played_like": 2226.0},
            {"role": "Technician", "team": 0, "played_like": 2043.0},
            {"role": "Technician", "team": 0, "played_like": 1565.0},
        ]
    }
    profile = build_profile_from_ks2_wiki("5-S2-1-6738824", mmr_data, playlike_data)
    assert profile.derived.playlike_spike_count >= 2
    assert profile.derived.playlike_spike_count_survivor >= 2
    assert profile.derived.playlike_spike_max is not None
    assert profile.derived.playlike_spike_max >= 400


def test_side_mmr_and_playlike_top3_averages():
    mmr_data = {
        "cores": {"survivor": 1600, "kerrigan": 2100},
        "roles_survivor": [
            {"role_name": "A", "core_mmr": 1600, "class_mmr": 100, "mmr": 1700, "plays": 5},
            {"role_name": "B", "core_mmr": 1600, "class_mmr": 50, "mmr": 1650, "plays": 3},
            {"role_name": "C", "core_mmr": 1600, "class_mmr": 20, "mmr": 1620, "plays": 1},
        ],
    }
    playlike_data = {
        "games": [
            {"role": "A", "team": 0, "played_like": 1800.0},
            {"role": "B", "team": 0, "played_like": 1700.0},
            {"role": "C", "team": 0, "played_like": 1600.0},
            {"role": "A", "team": 0, "played_like": 1500.0},
        ]
    }
    profile = build_profile_from_ks2_wiki("5-S2-1-1", mmr_data, playlike_data)
    d = profile.derived
    assert d.role_mmr_top3_avg_by_side["survivor"] == 1657
    assert d.role_mmr_avg_by_side["survivor"] == 1657
    assert d.playlike_inferred_top3_avg_by_side["survivor"] is not None
    assert d.playlike_inferred_avg_by_side["survivor"] is not None


def test_build_profile_from_fixture_file():
    fixture = FIXTURE_DIR / "ks2_wiki_sample.json"
    if not fixture.exists():
        return
    data = json.loads(fixture.read_text(encoding="utf-8"))
    profile = build_profile_from_ks2_wiki(
        "5-S2-1-12463673",
        data.get("mmr"),
        data.get("played_like"),
    )
    assert profile.derived.data_quality.has_mmr
    assert profile.derived.playlike_avg_all is not None
