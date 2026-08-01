from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from antismurf.models.rating_profile import PlayerRatingProfile


class CommunityRating(BaseModel):
    handle: str
    mmr: float | None = None
    mmr_playlike: float | None = None
    analyzed_at: datetime | None = None
    request_id: str | None = None
    raw: dict | None = None
    profile: PlayerRatingProfile | None = None

    @property
    def has_data(self) -> bool:
        if self.profile and self.profile.derived.data_quality.has_mmr:
            return True
        return self.mmr is not None or self.mmr_playlike is not None
