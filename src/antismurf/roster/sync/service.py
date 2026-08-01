from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from antismurf.config.settings import AppConfig
from antismurf.roster.parser import parse_roster_rows
from antismurf.roster.sources import collect_local_candidates
from antismurf.roster.store import PlayerRosterStore
from antismurf.roster.sync.base import RosterPushProvider
from antismurf.roster.sync.factory import create_roster_sync_provider
from antismurf.roster.sync.merge import merge_roster_with_local

logger = logging.getLogger(__name__)


@dataclass
class RosterSyncResult:
    ok: bool
    imported: int = 0
    added: int = 0
    updated_names: int = 0
    pushed: bool = False
    error: str | None = None


class RosterSyncService:
    def __init__(
        self,
        config: AppConfig,
        store: PlayerRosterStore | None = None,
    ) -> None:
        self._config = config
        self._store = store or PlayerRosterStore()
        self._last_sync_at: float = 0.0
        self._last_error: str | None = None

    @property
    def store(self) -> PlayerRosterStore:
        return self._store

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def update_config(self, config: AppConfig) -> None:
        self._config = config

    def should_sync(self, now: float | None = None) -> bool:
        if not self._config.roster_enabled:
            return False
        if not self._config.data_sources_confirmed:
            return False
        if self._config.roster_sync_provider.strip().lower() in ("", "disabled"):
            return False
        current = now if now is not None else time.monotonic()
        return current - self._last_sync_at >= self._config.roster_sync_interval_sec

    async def sync_now(self) -> RosterSyncResult:
        if not self._config.data_sources_confirmed:
            return RosterSyncResult(
                ok=False,
                error="请先在「数据源」中确认录像/规则/名册路径后再同步",
            )
        provider = create_roster_sync_provider(self._config)
        push_enabled = self._config.roster_sync_push_enabled
        try:
            remote_rows = await self._fetch_baseline_rows(provider)
            if push_enabled and isinstance(provider, RosterPushProvider):
                local_rows = await asyncio.to_thread(
                    self._collect_local_rows,
                )
                merged_rows, stats = merge_roster_with_local(
                    remote_rows,
                    local_rows,
                    former_name_prefix=self._config.roster_former_name_prefix,
                )
                await provider.push_rows(merged_rows)
                rows_to_import = merged_rows
                added = stats.added
                updated_names = stats.updated_names
                pushed = True
                logger.info(
                    "Roster push to %s: +%s new, %s name updates",
                    provider.describe(),
                    added,
                    updated_names,
                )
            else:
                rows_to_import = remote_rows
                added = 0
                updated_names = 0
                pushed = False

            entries = parse_roster_rows(
                rows_to_import,
                source=self._config.roster_sync_provider,
            )
            imported = await asyncio.to_thread(
                self._store.upsert_batch,
                entries,
                source=self._config.roster_sync_provider,
            )
            self._last_sync_at = time.monotonic()
            self._last_error = None
            logger.info(
                "Roster sync imported %s entries from %s",
                imported,
                provider.describe(),
            )
            return RosterSyncResult(
                ok=True,
                imported=imported,
                added=added,
                updated_names=updated_names,
                pushed=pushed,
            )
        except Exception as exc:
            self._last_error = str(exc)
            logger.warning("Roster sync failed: %s", exc)
            return RosterSyncResult(ok=False, error=str(exc))

    async def _fetch_baseline_rows(
        self,
        provider: object,
    ) -> list[dict[str, str]]:
        from antismurf.roster.sync.http_url import fetch_roster_rows_from_url

        rows = await provider.fetch_rows()  # type: ignore[attr-defined]
        fetch_url = (
            self._config.roster_sync_fetch_url.strip()
            or self._config.roster_sync_url.strip()
        )
        if not fetch_url:
            return rows
        headers: dict[str, str] = {}
        if self._config.roster_sync_api_key:
            headers["Authorization"] = f"Bearer {self._config.roster_sync_api_key}"
        http_rows = await fetch_roster_rows_from_url(
            fetch_url,
            timeout_sec=self._config.community_timeout_sec,
            headers=headers or None,
        )
        if not rows:
            return http_rows
        merged, _ = merge_roster_with_local(
            http_rows,
            rows,
            former_name_prefix=self._config.roster_former_name_prefix,
        )
        return merged

    def _collect_local_rows(self) -> list[dict[str, str]]:
        return collect_local_candidates(self._store)

    async def import_file(self, path: str) -> RosterSyncResult:
        from antismurf.roster.parser import parse_roster_file

        try:
            entries = await asyncio.to_thread(parse_roster_file, path)
            imported = await asyncio.to_thread(
                self._store.upsert_batch,
                entries,
                source="manual",
            )
            return RosterSyncResult(ok=True, imported=imported)
        except Exception as exc:
            return RosterSyncResult(ok=False, error=str(exc))
