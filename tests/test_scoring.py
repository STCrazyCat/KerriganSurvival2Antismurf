import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.config.settings import _project_root, load_config
from antismurf.models.community import CommunityRating
from antismurf.scoring.stage1_engine import Stage1Engine


def _default_config():
    from antismurf.config.expression_rules_io import expression_rules_from_raw_list
    from antismurf.scoring.presets import load_preset_rules

    config = load_config(_project_root() / "config" / "default.toml")
    config.expression_rules = expression_rules_from_raw_list(load_preset_rules("balanced"))
    config.handle_mark_rules = []
    config.handle_trust_rules = []
    # Tests must not inherit broken tier thresholds from config/user.toml merge.
    config.tier_medium = 40.0
    config.tier_high = 60.0
    config.tier_critical = 85.0
    return config


def test_handle_mark_adds_score():
    from antismurf.config.settings import HandleMarkRule

    config = _default_config()
    config.handle_mark_rules = [HandleMarkRule(handle="5-S2-1-500", weight=100)]
    engine = Stage1Engine(config)
    result = engine.evaluate(
        "5-S2-1-500",
        1,
        CommunityRating(handle="5-S2-1-500", mmr=3200, mmr_playlike=3100),
    )
    assert "handle_mark:5-S2-1-500" in result.triggered_rules
    assert result.score >= 100


def test_handle_trust_reduces_score():
    from antismurf.config.settings import HandleTrustRule

    config = _default_config()
    config.handle_trust_rules = [HandleTrustRule(handle="5-S2-1-500", weight=-20)]
    engine = Stage1Engine(config)
    result = engine.evaluate(
        "5-S2-1-500",
        1,
        CommunityRating(handle="5-S2-1-500", mmr=3200, mmr_playlike=3100),
    )
    assert "handle_trust:5-S2-1-500" in result.triggered_rules
    assert any("信任" in reason or "-20" in reason for reason in result.rule_reasons)


def test_playlike_top3_lift_rule_triggers():
    from antismurf.data.profile_builder import build_profile_from_ks2_wiki

    config = _default_config()
    engine = Stage1Engine(config)
    mmr_data = {
        "cores": {"survivor": 1500, "kerrigan": 1500},
        "roles_survivor": [
            {
                "role_name": "Marine",
                "core_mmr": 1500,
                "class_mmr": 100,
                "mmr": 1600,
                "plays": 5,
            }
        ],
    }
    games = []
    for idx, pl in enumerate([2600, 2550, 2500, 2400, 2300, 2200]):
        games.append(
            {
                "date": f"2026-06-{10 + idx:02d} 12:00:00",
                "role": "Marine",
                "team": 0,
                "played_like": pl + 100,
            }
        )
    profile = build_profile_from_ks2_wiki(
        "5-S2-1-13000000",
        mmr_data,
        {"games": games},
    )
    result = engine.evaluate(
        "5-S2-1-13000000",
        1,
        CommunityRating(
            handle="5-S2-1-13000000",
            mmr=1500,
            mmr_playlike=2500,
            profile=profile,
        ),
    )
    assert "playlike_top3_lift_1000" in result.triggered_rules
    assert result.score >= 100


def test_low_mmr_gap_low_tier():
    config = _default_config()
    engine = Stage1Engine(config)
    result = engine.evaluate(
        "5-S2-1-500",
        2,
        CommunityRating(handle="5-S2-1-500", mmr=3200, mmr_playlike=3100),
    )
    assert result.tier in ("low", "medium")


def test_parse_handle():
    from antismurf.models.player import parse_handle, parse_handle_parts, is_valid_handle

    parts = parse_handle_parts("5-S2-1-1234567")
    assert parts is not None
    assert parts.server_id == 5
    assert parts.realm_id == 1
    assert parts.player_id == 1234567
    assert parse_handle("5-S2-1-1234567") == ("5-S2-1-1234567", 1234567)
    assert is_valid_handle("5-S2-1-1234567")
    assert not is_valid_handle("Player#21698")


def test_same_match_kerrigan_spike_adds_score():
    config = _default_config()
    engine = Stage1Engine(config)
    rating = CommunityRating(handle="5-S2-1-500", mmr=3200, mmr_playlike=3100)
    base = engine.evaluate(
        "5-S2-1-500", 1, rating, kerrigan_same_match_spike_count=0
    )
    result = engine.evaluate(
        "5-S2-1-500", 1, rating, kerrigan_same_match_spike_count=3
    )
    assert "same_match_kerrigan_spike" in result.triggered_rules
    assert any("3次" in reason and "凯瑞甘" in reason for reason in result.rule_reasons)
    assert result.score == min(100.0, base.score + 60)
