from __future__ import annotations

import logging
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from antismurf.community.protocol import CommunityProvider
from antismurf.community.response_parser import parse_rating_payload
from antismurf.models.community import CommunityRating

logger = logging.getLogger(__name__)


class HttpCommunityClient:
    """HTTP implementation of CommunityProvider."""

    def __init__(
        self,
        base_url: str,
        submit_path: str = "/api/v1/handles",
        rating_path: str = "/api/v1/handles/{handle}",
        api_key: str = "",
        timeout_sec: float = 10.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._submit_path = submit_path
        self._rating_path = rating_path
        self._api_key = api_key
        self._timeout = timeout_sec
        self._pending: dict[str, str] = {}

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _rating_url(self, handle: str) -> str:
        encoded = quote(handle, safe="")
        path = self._rating_path.replace("{handle}", encoded)
        if "{handle}" in self._rating_path:
            return f"{self._base}{path}"
        return f"{self._base}{path.rstrip('/')}/{encoded}"

    async def submit_handle(self, handle: str) -> str:
        url = f"{self._base}{self._submit_path}"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                url,
                json={"handle": handle},
                headers=self._headers(),
            )
            if resp.status_code >= 400:
                logger.error("Community submit failed: %s", resp.text)
                return handle
            data = resp.json()
            request_id = str(data.get("request_id", handle))
            self._pending[handle] = request_id
            return request_id

    async def fetch_rating(self, request_id: str) -> CommunityRating | None:
        for handle, rid in self._pending.items():
            if rid == request_id:
                return await self.get_rating_by_handle(handle)
        return None

    async def get_rating_by_handle(self, handle: str) -> CommunityRating:
        url = self._rating_url(handle)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(url, headers=self._headers())
            if resp.status_code == 404:
                return CommunityRating(handle=handle)
            if resp.status_code >= 400:
                logger.error("Community rating failed: %s", resp.text)
                return CommunityRating(handle=handle)
            data = resp.json()
        mmr, playlike = parse_rating_payload(data)
        return CommunityRating(
            handle=handle,
            mmr=mmr,
            mmr_playlike=playlike,
            analyzed_at=datetime.now(timezone.utc),
            request_id=self._pending.get(handle),
            raw=data if isinstance(data, dict) else None,
        )
