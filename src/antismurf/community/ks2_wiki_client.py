from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from antismurf.community.ks2_endpoints import (
    KS2_WIKI_BASE_URL,
    KS2_WIKI_ENDPOINTS,
    Ks2EndpointProfile,
    endpoints_for_base_url,
)
from antismurf.community.protocol import CommunityProvider
from antismurf.data.profile_builder import (
    build_profile_from_ks2_wiki,
    summary_from_profile,
)
from antismurf.models.community import CommunityRating

logger = logging.getLogger(__name__)


class Ks2CommunityClient:
    """Fetch MMR + played_like from KS2 Wiki or 194823 tool site JSON APIs."""

    def __init__(
        self,
        base_url: str = KS2_WIKI_BASE_URL,
        timeout_sec: float = 10.0,
        *,
        endpoints: Ks2EndpointProfile | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout_sec
        self._endpoints = endpoints or endpoints_for_base_url(self._base)

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "User-Agent": "AntiSmurf/1.0 (KS2 host tool)",
        }

    async def submit_handle(self, handle: str) -> str:
        return handle

    async def fetch_rating(self, request_id: str) -> CommunityRating | None:
        return await self.get_rating_by_handle(request_id)

    async def _get_json(
        self,
        client: httpx.AsyncClient,
        *,
        base: str,
        path: str,
        param_name: str,
        handle: str,
    ) -> tuple[int, dict | None]:
        resp = await client.get(
            f"{base}{path}",
            params={param_name: handle},
            headers=self._headers(),
        )
        if resp.status_code == 204:
            return resp.status_code, None
        if resp.status_code >= 400:
            return resp.status_code, None
        if not resp.text.strip():
            return resp.status_code, None
        data = resp.json()
        return resp.status_code, data if isinstance(data, dict) else None

    async def get_rating_by_handle(self, handle: str) -> CommunityRating:
        ep = self._endpoints
        playlike_base = ep.played_like_base or self._base

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            mmr_status, mmr_data = await self._get_json(
                client,
                base=self._base,
                path=ep.mmr_path,
                param_name=ep.mmr_param,
                handle=handle,
            )
            if mmr_status == 204 or mmr_data is None:
                if mmr_status >= 400 and mmr_status != 204:
                    logger.error(
                        "KS2 MMR lookup failed for %s via %s: HTTP %s",
                        handle,
                        self._base,
                        mmr_status,
                    )
                return CommunityRating(handle=handle)

            playlike_data = None
            if ep.played_like_path:
                _, playlike_data = await self._get_json(
                    client,
                    base=playlike_base,
                    path=ep.played_like_path,
                    param_name=ep.played_like_param,
                    handle=handle,
                )

        profile = build_profile_from_ks2_wiki(handle, mmr_data, playlike_data)
        mmr, playlike = summary_from_profile(profile)
        raw: dict = {"mmr": mmr_data}
        if playlike_data:
            raw["played_like"] = playlike_data

        return CommunityRating(
            handle=handle,
            mmr=mmr,
            mmr_playlike=playlike,
            analyzed_at=datetime.now(timezone.utc),
            request_id=handle,
            raw=raw,
            profile=profile,
        )


# Backward-compatible alias
Ks2WikiClient = Ks2CommunityClient
