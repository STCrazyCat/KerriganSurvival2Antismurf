from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import aiosqlite


@dataclass
class EvaluationLogEntry:
    handle: str
    tier: str
    score: float
    rules: list[str]
    created_at: datetime


@dataclass
class KickLogEntry:
    handle: str
    success: bool
    dry_run: bool
    created_at: datetime

_SCHEMA = """
CREATE TABLE IF NOT EXISTS whitelist (
    handle TEXT PRIMARY KEY,
    added_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    handle TEXT NOT NULL,
    tier TEXT NOT NULL,
    score REAL NOT NULL,
    rules TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS profile_refs (
    handle TEXT PRIMARY KEY,
    region_id INTEGER NOT NULL,
    realm_id INTEGER NOT NULL,
    profile_id INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS blocklist (
    handle TEXT PRIMARY KEY,
    added_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS kick_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    handle TEXT NOT NULL,
    success INTEGER NOT NULL,
    dry_run INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS player_sightings (
    handle TEXT PRIMARY KEY,
    snapshot_json TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    seen_count INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_player_sightings_last_seen
    ON player_sightings(last_seen_at DESC);
"""


class PlayerStore:
    def __init__(self, db_path: str | Path) -> None:
        self._path = Path(db_path)

    async def init(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._path) as db:
            await db.executescript(_SCHEMA)
            await db.commit()

    async def is_whitelisted(self, handle: str) -> bool:
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT 1 FROM whitelist WHERE handle = ?", (handle,)
            ) as cur:
                return await cur.fetchone() is not None

    async def add_whitelist(self, handle: str) -> None:
        from datetime import datetime, timezone

        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO whitelist (handle, added_at) VALUES (?, ?)",
                (handle, datetime.now(timezone.utc).isoformat()),
            )
            await db.commit()

    async def remove_whitelist(self, handle: str) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute("DELETE FROM whitelist WHERE handle = ?", (handle,))
            await db.commit()

    async def log_evaluation(
        self, handle: str, tier: str, score: float, rules: list[str]
    ) -> None:
        from datetime import datetime, timezone

        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT INTO evaluations (handle, tier, score, rules, created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    handle,
                    tier,
                    score,
                    json.dumps(rules),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            await db.commit()

    async def get_profile_ref(
        self, handle: str
    ) -> tuple[int, int, int] | None:
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT region_id, realm_id, profile_id FROM profile_refs WHERE handle = ?",
                (handle,),
            ) as cur:
                row = await cur.fetchone()
                if row is None:
                    return None
                return int(row[0]), int(row[1]), int(row[2])

    async def save_profile_ref(
        self,
        handle: str,
        region_id: int,
        realm_id: int,
        profile_id: int,
    ) -> None:
        from datetime import datetime, timezone

        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                INSERT OR REPLACE INTO profile_refs
                (handle, region_id, realm_id, profile_id, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    handle,
                    region_id,
                    realm_id,
                    profile_id,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            await db.commit()

    async def load_blocklist_handles(self) -> set[str]:
        async with aiosqlite.connect(self._path) as db:
            async with db.execute("SELECT handle FROM blocklist") as cur:
                rows = await cur.fetchall()
                return {row[0] for row in rows}

    async def is_blocklisted(self, handle: str) -> bool:
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT 1 FROM blocklist WHERE handle = ?", (handle,)
            ) as cur:
                return await cur.fetchone() is not None

    async def add_blocklist(self, handle: str) -> None:
        from datetime import datetime, timezone

        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO blocklist (handle, added_at) VALUES (?, ?)",
                (handle, datetime.now(timezone.utc).isoformat()),
            )
            await db.commit()

    async def remove_blocklist(self, handle: str) -> None:
        async with aiosqlite.connect(self._path) as db:
            await db.execute("DELETE FROM blocklist WHERE handle = ?", (handle,))
            await db.commit()

    async def list_evaluations(self, limit: int = 100) -> list[EvaluationLogEntry]:
        from datetime import datetime

        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                """
                SELECT handle, tier, score, rules, created_at
                FROM evaluations ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ) as cur:
                rows = await cur.fetchall()
        entries: list[EvaluationLogEntry] = []
        for row in rows:
            entries.append(
                EvaluationLogEntry(
                    handle=row[0],
                    tier=row[1],
                    score=float(row[2]),
                    rules=json.loads(row[3]),
                    created_at=datetime.fromisoformat(row[4]),
                )
            )
        return entries

    async def log_kick(self, handle: str, success: bool, dry_run: bool) -> None:
        from datetime import datetime, timezone

        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                INSERT INTO kick_log (handle, success, dry_run, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    handle,
                    int(success),
                    int(dry_run),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            await db.commit()

    async def list_kicks(self, limit: int = 50) -> list[KickLogEntry]:
        from datetime import datetime

        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                """
                SELECT handle, success, dry_run, created_at
                FROM kick_log ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ) as cur:
                rows = await cur.fetchall()
        return [
            KickLogEntry(
                handle=row[0],
                success=bool(row[1]),
                dry_run=bool(row[2]),
                created_at=datetime.fromisoformat(row[3]),
            )
            for row in rows
        ]

    async def upsert_player_sighting(self, record) -> None:
        from datetime import datetime, timezone

        from antismurf.data.player_display import sighting_snapshot_from_record
        from antismurf.models.evaluation import PlayerRecord

        if not isinstance(record, PlayerRecord):
            return
        handle = record.handle.strip()
        if not handle:
            return

        now = datetime.now(timezone.utc).isoformat()
        snapshot = json.dumps(sighting_snapshot_from_record(record), ensure_ascii=False)
        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                "SELECT first_seen_at, seen_count FROM player_sightings WHERE handle = ?",
                (handle,),
            ) as cur:
                row = await cur.fetchone()
            if row is None:
                await db.execute(
                    """
                    INSERT INTO player_sightings
                    (handle, snapshot_json, first_seen_at, last_seen_at, seen_count)
                    VALUES (?, ?, ?, ?, 1)
                    """,
                    (handle, snapshot, now, now),
                )
            else:
                first_seen_at, seen_count = row[0], int(row[1]) + 1
                await db.execute(
                    """
                    UPDATE player_sightings
                    SET snapshot_json = ?, last_seen_at = ?, seen_count = ?
                    WHERE handle = ?
                    """,
                    (snapshot, now, seen_count, handle),
                )
            await db.commit()

    async def list_player_sightings(self, limit: int = 200):
        from datetime import datetime

        from antismurf.storage.sightings import entry_from_row, parse_snapshot

        async with aiosqlite.connect(self._path) as db:
            async with db.execute(
                """
                SELECT handle, snapshot_json, first_seen_at, last_seen_at, seen_count
                FROM player_sightings
                ORDER BY last_seen_at DESC
                LIMIT ?
                """,
                (limit,),
            ) as cur:
                rows = await cur.fetchall()
        entries = []
        for row in rows:
            snapshot = parse_snapshot(row[1])
            entries.append(
                entry_from_row(
                    row[0],
                    snapshot,
                    first_seen_at=datetime.fromisoformat(row[2]),
                    last_seen_at=datetime.fromisoformat(row[3]),
                    seen_count=int(row[4]),
                )
            )
        return entries
