from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

Side = Literal["kerrigan", "survivor"]
Archetype = Literal["hunter", "defender", "builder", "support"]


class RoleMmr(BaseModel):
    role_name: str
    core_mmr: float | None = None
    class_mmr: float | None = None
    mmr: float | None = None
    side: Side | None = None
    archetype: Archetype | None = None
    wins: int = 0
    plays: int = 0
    win_rate: float | None = None


class PlaylikeGame(BaseModel):
    role: str
    team: int | None = None
    played_like: float | None = None
    estimated: float | None = None
    date: str = ""
    side: Side | None = None
    archetype: Archetype | None = None
    inferred_core: float | None = None
    lift_over_core: float | None = None


class CoreMmrPair(BaseModel):
    kerrigan: float | None = None
    survivor: float | None = None

    @property
    def max_value(self) -> float | None:
        values = [v for v in (self.kerrigan, self.survivor) if v is not None]
        return max(values) if values else None

    @property
    def min_value(self) -> float | None:
        values = [v for v in (self.kerrigan, self.survivor) if v is not None]
        return min(values) if values else None


class CorePlaylikePair(BaseModel):
    kerrigan: float | None = None
    survivor: float | None = None

    @property
    def max_value(self) -> float | None:
        values = [v for v in (self.kerrigan, self.survivor) if v is not None]
        return max(values) if values else None

    @property
    def min_value(self) -> float | None:
        values = [v for v in (self.kerrigan, self.survivor) if v is not None]
        return min(values) if values else None


class DataQuality(BaseModel):
    has_mmr: bool = False
    has_playlike: bool = False
    playlike_game_count: int = 0
    inferred_kerrigan_games: int = 0
    inferred_survivor_games: int = 0
    missing_class_offset_count: int = 0
    community_match_count: int = 0


class DerivedMetrics(BaseModel):
    core_mmr: CoreMmrPair = Field(default_factory=CoreMmrPair)
    core_playlike: CorePlaylikePair = Field(default_factory=CorePlaylikePair)
    gap_core_kerrigan: float | None = None
    gap_core_survivor: float | None = None
    gap_core_max: float | None = None
    lift_core_kerrigan: float | None = None
    lift_core_survivor: float | None = None
    lift_core_max: float | None = None
    playlike_spike_count: int = 0
    playlike_spike_max: float | None = None
    playlike_spike_avg: float | None = None
    playlike_spike_count_survivor: int = 0
    playlike_spike_count_kerrigan: int = 0
    playlike_avg_all: float | None = None
    playlike_avg_by_side: dict[str, float] = Field(default_factory=dict)
    playlike_avg_by_archetype: dict[str, float] = Field(default_factory=dict)
    playlike_avg_by_role: dict[str, float] = Field(default_factory=dict)
    role_mmr_top3_avg_by_side: dict[str, float] = Field(default_factory=dict)
    role_mmr_avg_by_side: dict[str, float] = Field(default_factory=dict)
    playlike_inferred_top3_avg_by_side: dict[str, float] = Field(default_factory=dict)
    playlike_inferred_avg_by_side: dict[str, float] = Field(default_factory=dict)
    lift_top3_core_max: float | None = None
    playlike_recent_growth: float | None = None
    class_mmr_max_by_side: dict[str, float] = Field(default_factory=dict)
    class_mmr_avg_by_archetype: dict[str, float] = Field(default_factory=dict)
    data_quality: DataQuality = Field(default_factory=DataQuality)


class PlayerRatingProfile(BaseModel):
    handle: str
    profile_id: int | None = None
    core_mmr: CoreMmrPair = Field(default_factory=CoreMmrPair)
    roles: dict[str, RoleMmr] = Field(default_factory=dict)
    playlike_games: list[PlaylikeGame] = Field(default_factory=list)
    derived: DerivedMetrics = Field(default_factory=DerivedMetrics)

    @property
    def summary_mmr(self) -> float | None:
        return self.core_mmr.min_value

    @property
    def summary_playlike(self) -> float | None:
        return self.derived.playlike_avg_all
