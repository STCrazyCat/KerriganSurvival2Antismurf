from __future__ import annotations

from antismurf.models.community import CommunityRating


class DisabledCommunityProvider:
    """No-op community backend: no network, no local stub lookups."""

    async def submit_handle(self, handle: str) -> str:
        return ""

    async def fetch_rating(self, request_id: str) -> CommunityRating | None:
        return None

    async def get_rating_by_handle(self, handle: str) -> CommunityRating:
        return CommunityRating(handle=handle)
