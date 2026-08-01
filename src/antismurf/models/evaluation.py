from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from antismurf.models.community import CommunityRating
from antismurf.models.player import SuspicionTier

MatchDecision = Literal["win", "loss", "undecided"]


class MatchSummary(BaseModel):
    map_name: str = ""
    game_type: str = ""
    decision: MatchDecision = "undecided"
    played_at: datetime | None = None


class Stage1Result(BaseModel):
    handle: str
    slot_index: int
    tier: SuspicionTier
    score: float
    triggered_rules: list[str] = Field(default_factory=list)
    rule_reasons: list[str] = Field(default_factory=list)
    community: CommunityRating
    handle_discriminator: int | None = None


class PlayerRecord(BaseModel):
    """Aggregated state for GUI and orchestrator."""

    handle: str
    slot_index: int
    discriminator: int | None = None
    display_name: str = ""
    team_name: str = ""
    remark: str = ""
    profile_id: int | None = None
    profile_ref: str = ""
    tier: SuspicionTier = "low"
    score: float = 0.0
    triggered_rules: list[str] = Field(default_factory=list)
    rule_reasons: list[str] = Field(default_factory=list)
    community: CommunityRating | None = None
    match_history: list[MatchSummary] = Field(default_factory=list)
    whitelisted: bool = False
    first_seen_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
