"""Format player stats for GUI and persisted sighting snapshots."""

from __future__ import annotations

from antismurf.models.evaluation import PlayerRecord
from antismurf.models.rating_profile import PlayerRatingProfile


def _fmt_num(value: float | None) -> str:
    if value is None:
        return "-"
    if value == int(value):
        return str(int(value))
    return f"{value:.0f}"


def format_faction_mmr_block(
    profile: PlayerRatingProfile | None,
    side: str,
) -> str:
    if profile is None:
        return "-"
    derived = profile.derived
    core = (
        profile.core_mmr.survivor
        if side == "survivor"
        else profile.core_mmr.kerrigan
    )
    pl_avg = derived.playlike_avg_by_side.get(side)
    if core is None and pl_avg is None:
        return "-"
    parts: list[str] = []
    if core is not None:
        parts.append(f"核心 {_fmt_num(core)}")
    if pl_avg is not None:
        if core is not None:
            parts.append(f"差 {_fmt_num(core - pl_avg)}")
        else:
            parts.append(f"均值 {_fmt_num(pl_avg)}")
    return " · ".join(parts)


def format_faction_playlike_block(
    profile: PlayerRatingProfile | None,
    side: str,
) -> str:
    if profile is None:
        return "-"
    derived = profile.derived
    top3 = derived.playlike_inferred_top3_avg_by_side.get(side)
    avg = derived.playlike_inferred_avg_by_side.get(side)
    if top3 is None and avg is None:
        return "-"
    parts: list[str] = []
    if top3 is not None:
        parts.append(f"前三 {_fmt_num(top3)}")
    if avg is not None:
        parts.append(f"均值 {_fmt_num(avg)}")
    return " · ".join(parts)


def faction_stats_for_record(record: PlayerRecord) -> dict[str, str]:
    profile = record.community.profile if record.community else None
    return {
        "s_mmr": format_faction_mmr_block(profile, "survivor"),
        "s_pl": format_faction_playlike_block(profile, "survivor"),
        "k_mmr": format_faction_mmr_block(profile, "kerrigan"),
        "k_pl": format_faction_playlike_block(profile, "kerrigan"),
    }


def core_gap_summary(record: PlayerRecord) -> str:
    profile = record.community.profile if record.community else None
    if profile and profile.derived.playlike_spike_count:
        spike = profile.derived.playlike_spike_count
        mx = profile.derived.playlike_spike_max
        if mx is not None:
            return f"{spike}局+{mx:.0f}"
        return f"{spike}局"
    if profile and profile.derived.lift_core_max is not None:
        return f"+{profile.derived.lift_core_max:.0f}"
    return "-"


def sighting_snapshot_from_record(record: PlayerRecord) -> dict:
    stats = faction_stats_for_record(record)
    community = record.community
    profile = community.profile if community else None
    derived = profile.derived if profile else None
    snapshot = {
        "handle": record.handle,
        "display_name": record.display_name or "",
        "team_name": record.team_name or "",
        "slot_index": record.slot_index,
        "tier": record.tier,
        "score": record.score,
        "triggered_rules": list(record.triggered_rules),
        "remark": record.remark or "",
        "mmr": community.mmr if community else None,
        "mmr_playlike": community.mmr_playlike if community else None,
        "survivor_mmr": stats["s_mmr"],
        "survivor_pl": stats["s_pl"],
        "kerrigan_mmr": stats["k_mmr"],
        "kerrigan_pl": stats["k_pl"],
        "core_gap": core_gap_summary(record),
    }
    if profile is not None:
        snapshot["survivor_core"] = profile.core_mmr.survivor
        snapshot["kerrigan_core"] = profile.core_mmr.kerrigan
    if derived is not None:
        snapshot["survivor_pl_top3"] = derived.playlike_inferred_top3_avg_by_side.get(
            "survivor"
        )
        snapshot["kerrigan_pl_top3"] = derived.playlike_inferred_top3_avg_by_side.get(
            "kerrigan"
        )
        snapshot["lift_top3_core_max"] = derived.lift_top3_core_max
        snapshot["community_match_count"] = derived.data_quality.community_match_count
    return snapshot


def sighting_snapshot_from_community(handle: str, community) -> dict:
    """Build numeric snapshot from live community data for history comparison."""
    from antismurf.models.community import CommunityRating
    from antismurf.models.evaluation import PlayerRecord

    if not isinstance(community, CommunityRating):
        return {"handle": handle}
    record = PlayerRecord(
        handle=handle,
        slot_index=0,
        tier="low",
        score=0.0,
        community=community,
    )
    return sighting_snapshot_from_record(record)
