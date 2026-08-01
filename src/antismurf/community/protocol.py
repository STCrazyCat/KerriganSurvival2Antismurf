from __future__ import annotations

from typing import Protocol, runtime_checkable

from antismurf.models.community import CommunityRating


@runtime_checkable
class CommunityProvider(Protocol):
    """Community server contract: submit a handle, then read MMR / MMR_playlike."""

    async def submit_handle(self, handle: str) -> str:
        """Register a handle for analysis; returns a request id for polling."""
        ...

    async def fetch_rating(self, request_id: str) -> CommunityRating | None:
        """Look up rating by request id from a prior submit_handle call."""
        ...

    async def get_rating_by_handle(self, handle: str) -> CommunityRating:
        """Return MMR data for a handle (empty rating when unknown)."""
        ...
