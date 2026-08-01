"""Persisted player sighting snapshots."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime


@dataclass
class PlayerSightingEntry:
    handle: str
    display_name: str
    team_name: str
    slot_index: int
    tier: str
    score: float
    triggered_rules: list[str]
    remark: str
    mmr: float | None
    mmr_playlike: float | None
    survivor_mmr: str
    survivor_pl: str
    kerrigan_mmr: str
    kerrigan_pl: str
    core_gap: str
    snapshot: dict
    first_seen_at: datetime
    last_seen_at: datetime
    seen_count: int = 1

    @property
    def nickname(self) -> str:
        return self.display_name or "-"

    @property
    def tier_label(self) -> str:
        labels = {"low": "低", "medium": "中", "high": "高", "critical": "极高"}
        return labels.get(self.tier, self.tier)


def entry_from_row(
    handle: str,
    snapshot: dict,
    *,
    first_seen_at: datetime,
    last_seen_at: datetime,
    seen_count: int,
) -> PlayerSightingEntry:
    return PlayerSightingEntry(
        handle=handle,
        display_name=str(snapshot.get("display_name", "")),
        team_name=str(snapshot.get("team_name", "")),
        slot_index=int(snapshot.get("slot_index", 0)),
        tier=str(snapshot.get("tier", "low")),
        score=float(snapshot.get("score", 0)),
        triggered_rules=list(snapshot.get("triggered_rules", [])),
        remark=str(snapshot.get("remark", "")),
        mmr=_optional_float(snapshot.get("mmr")),
        mmr_playlike=_optional_float(snapshot.get("mmr_playlike")),
        survivor_mmr=str(snapshot.get("survivor_mmr", "-")),
        survivor_pl=str(snapshot.get("survivor_pl", "-")),
        kerrigan_mmr=str(snapshot.get("kerrigan_mmr", "-")),
        kerrigan_pl=str(snapshot.get("kerrigan_pl", "-")),
        core_gap=str(snapshot.get("core_gap", "-")),
        snapshot=dict(snapshot),
        first_seen_at=first_seen_at,
        last_seen_at=last_seen_at,
        seen_count=seen_count,
    )


def parse_snapshot(raw: str) -> dict:
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("invalid sighting snapshot")
    return data


def _optional_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
