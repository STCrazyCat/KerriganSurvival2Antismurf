from __future__ import annotations

import logging
from typing import Any

import httpx

from antismurf.config.settings import AppConfig
from antismurf.roster.parser import parse_roster_bytes
from antismurf.roster.sync.base import RosterPushProvider

logger = logging.getLogger(__name__)


async def fetch_roster_rows_from_url(
    url: str,
    *,
    timeout_sec: float = 30.0,
    headers: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    if not url.strip():
        return []
    async with httpx.AsyncClient(timeout=timeout_sec, follow_redirects=True) as client:
        response = await client.get(url.strip(), headers=headers or {})
        response.raise_for_status()
        return parse_roster_bytes(response.content, hint=url)


async def push_roster_rows_to_url(
    url: str,
    rows: list[dict[str, str]],
    *,
    timeout_sec: float = 30.0,
    api_key: str = "",
) -> None:
    if not url.strip():
        raise ValueError("未配置名册上传 URL")
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload: dict[str, Any] = {"version": 1, "rows": rows}
    async with httpx.AsyncClient(timeout=timeout_sec, follow_redirects=True) as client:
        response = await client.post(url.strip(), json=payload, headers=headers)
        response.raise_for_status()
        logger.info("Pushed %s roster rows to %s", len(rows), url)


class HttpUrlRosterSyncProvider:
    """Fetch roster export via HTTP GET; push merged rows via HTTP POST JSON."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._fetch_url = (
            config.roster_sync_fetch_url.strip() or config.roster_sync_url.strip()
        )
        self._push_url = config.roster_sync_push_url.strip()

    def describe(self) -> str:
        return f"http_url:fetch={self._fetch_url or '-'} push={self._push_url or '-'}"

    async def fetch_rows(self) -> list[dict[str, str]]:
        if not self._fetch_url:
            return []
        return await fetch_roster_rows_from_url(
            self._fetch_url,
            timeout_sec=self._config.community_timeout_sec,
            headers=self._auth_headers(),
        )

    async def push_rows(self, rows: list[dict[str, str]]) -> None:
        if not self._push_url:
            raise ValueError("未配置 roster.sync.push_url，无法上传到在线文档")
        await push_roster_rows_to_url(
            self._push_url,
            rows,
            timeout_sec=self._config.community_timeout_sec,
            api_key=self._config.roster_sync_api_key,
        )

    def _auth_headers(self) -> dict[str, str]:
        if self._config.roster_sync_api_key:
            return {"Authorization": f"Bearer {self._config.roster_sync_api_key}"}
        return {}


class LocalFileWithHttpPushProvider:
    """Read/write local xlsx/csv and optionally POST merges to a webhook URL."""

    def __init__(self, config: AppConfig, local: RosterPushProvider) -> None:
        self._config = config
        self._local = local
        self._push_url = config.roster_sync_push_url.strip()

    def describe(self) -> str:
        return f"{self._local.describe()}+http_push"

    async def fetch_rows(self) -> list[dict[str, str]]:
        return await self._local.fetch_rows()

    async def push_rows(self, rows: list[dict[str, str]]) -> None:
        await self._local.push_rows(rows)
        if self._push_url:
            await push_roster_rows_to_url(
                self._push_url,
                rows,
                timeout_sec=self._config.community_timeout_sec,
                api_key=self._config.roster_sync_api_key,
            )
