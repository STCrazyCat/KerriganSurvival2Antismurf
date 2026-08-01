from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class RosterSyncProvider(Protocol):
    def describe(self) -> str: ...

    async def fetch_rows(self) -> list[dict[str, str]]: ...


@runtime_checkable
class RosterPushProvider(RosterSyncProvider, Protocol):
    async def push_rows(self, rows: list[dict[str, str]]) -> None: ...
