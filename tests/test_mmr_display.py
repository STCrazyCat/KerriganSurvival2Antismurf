import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.app.mmr_display import format_faction_mmr_block, format_faction_playlike_block
from antismurf.data.profile_builder import build_profile_from_ks2_wiki
from antismurf.models.community import CommunityRating
from antismurf.models.evaluation import PlayerRecord


def test_mmr_display_blocks():
    profile = build_profile_from_ks2_wiki(
        "5-S2-1-1",
        {"cores": {"survivor": 1607, "kerrigan": 2099}},
        None,
    )
    mmr_text = format_faction_mmr_block(profile, "survivor")
    assert "核心 1607" in mmr_text
    pl_text = format_faction_playlike_block(profile, "survivor")
    assert pl_text == "-"

    record = PlayerRecord(
        handle="5-S2-1-1",
        slot_index=0,
        community=CommunityRating(handle="5-S2-1-1", profile=profile),
    )
    from antismurf.app.mmr_display import faction_stats_for_record

    stats = faction_stats_for_record(record)
    assert "核心 1607" in stats["s_mmr"]
    assert "核心 2099" in stats["k_mmr"]


def test_mmr_display_blocks_with_playlike_gap():
    from antismurf.models.rating_profile import CoreMmrPair, PlayerRatingProfile

    profile = PlayerRatingProfile(
        handle="5-S2-1-2",
        core_mmr=CoreMmrPair(survivor=1607, kerrigan=2099),
    )
    profile.derived.playlike_avg_by_side = {"survivor": 1400, "kerrigan": 1500}

    survivor = format_faction_mmr_block(profile, "survivor")
    assert "核心 1607" in survivor
    assert "差 207" in survivor
    assert "前三" not in survivor

    kerrigan = format_faction_mmr_block(profile, "kerrigan")
    assert "核心 2099" in kerrigan
    assert "差 599" in kerrigan
