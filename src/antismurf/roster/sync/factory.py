from __future__ import annotations

import asyncio
from pathlib import Path

from antismurf.config.settings import AppConfig, _project_root
from antismurf.roster.parser import parse_roster_file
from antismurf.roster.sync.base import RosterPushProvider, RosterSyncProvider
from antismurf.roster.writer import write_roster_file


class DisabledRosterSyncProvider:
    def describe(self) -> str:
        return "disabled"

    async def fetch_rows(self) -> list[dict[str, str]]:
        return []


class LocalFileRosterSyncProvider:
    def __init__(self, path: str | Path) -> None:
        self._path = self._resolve_path(path)

    @staticmethod
    def _resolve_path(path: str | Path) -> Path:
        file_path = Path(path)
        if not file_path.is_absolute():
            file_path = _project_root() / file_path
        return file_path

    def describe(self) -> str:
        return f"local_file:{self._path}"

    async def fetch_rows(self) -> list[dict[str, str]]:
        if not self._path.exists():
            return []
        entries = await asyncio.to_thread(parse_roster_file, self._path)
        return [
            {
                "display_name": entry.display_name,
                "handle": entry.handle,
                "remark": entry.remark,
            }
            for entry in entries
        ]

    async def push_rows(self, rows: list[dict[str, str]]) -> None:
        await asyncio.to_thread(write_roster_file, self._path, rows)


from antismurf.roster.sync.http_url import HttpUrlRosterSyncProvider, LocalFileWithHttpPushProvider


class TencentDocsRosterSyncProvider:
    """Phase 2 placeholder for Tencent Docs Open API."""

    def describe(self) -> str:
        return "tencent_docs"

    async def fetch_rows(self) -> list[dict[str, str]]:
        raise NotImplementedError(
            "tencent_docs API 同步尚未实现；请使用 http_url 或 local_file 方式"
        )


def create_roster_sync_provider(config: AppConfig) -> RosterSyncProvider:
    provider = config.roster_sync_provider.strip().lower()
    if provider in ("", "disabled"):
        return DisabledRosterSyncProvider()
    if provider == "local_file":
        local = LocalFileRosterSyncProvider(config.roster_sync_path)
        if config.roster_sync_push_url.strip():
            return LocalFileWithHttpPushProvider(config, local)
        return local
    if provider == "http_url":
        return HttpUrlRosterSyncProvider(config)
    if provider == "tencent_docs":
        return TencentDocsRosterSyncProvider()
    raise ValueError(f"未知名册同步 provider: {provider}")
