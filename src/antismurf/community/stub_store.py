from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from antismurf.community.response_parser import parse_rating_payload
from antismurf.data.profile_builder import build_profile_from_stub_summary
from antismurf.models.community import CommunityRating


class StubCommunityStore:
    """Local stub: reads MMR data from ``community_stub.json``."""

    def __init__(self, stub_path: str | Path) -> None:
        self._path = Path(stub_path)
        self._pending: dict[str, str] = {}

    def _load(self) -> dict:
        if not self._path.exists():
            return {}
        with open(self._path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}

    async def submit_handle(self, handle: str) -> str:
        request_id = str(uuid.uuid4())
        self._pending[handle] = request_id
        return request_id

    async def fetch_rating(self, request_id: str) -> CommunityRating | None:
        for handle, rid in self._pending.items():
            if rid == request_id:
                return await self.get_rating_by_handle(handle)
        return None

    async def get_rating_by_handle(self, handle: str) -> CommunityRating:
        entry = self._load().get(handle, {})
        if not isinstance(entry, dict):
            entry = {}
        mmr, playlike = parse_rating_payload(entry)
        profile = build_profile_from_stub_summary(handle, entry)
        return CommunityRating(
            handle=handle,
            mmr=mmr,
            mmr_playlike=playlike,
            analyzed_at=datetime.now(timezone.utc),
            request_id=self._pending.get(handle),
            raw=entry or None,
            profile=profile,
        )
