from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from antismurf.config.settings import _project_root
from antismurf.roster.models import PlayerRosterEntry

_SCHEMA = """
CREATE TABLE IF NOT EXISTS player_roster (
    handle TEXT PRIMARY KEY,
    display_name TEXT NOT NULL DEFAULT '',
    remark TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual'
);
CREATE INDEX IF NOT EXISTS idx_roster_display_name ON player_roster(display_name);
"""


class PlayerRosterStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        root = _project_root()
        self._path = Path(db_path or root / "data" / "player_roster.db")

    @property
    def path(self) -> Path:
        return self._path

    def init(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._path) as db:
            db.executescript(_SCHEMA)
            db.commit()

    def upsert_batch(self, entries: list[PlayerRosterEntry], *, source: str | None = None) -> int:
        if not entries:
            return 0
        now = datetime.now(timezone.utc).isoformat()
        count = 0
        with sqlite3.connect(self._path) as db:
            for entry in entries:
                if not entry.handle:
                    continue
                db.execute(
                    """
                    INSERT INTO player_roster (handle, display_name, remark, updated_at, source)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(handle) DO UPDATE SET
                        display_name = excluded.display_name,
                        remark = excluded.remark,
                        updated_at = excluded.updated_at,
                        source = excluded.source
                    """,
                    (
                        entry.handle,
                        entry.display_name,
                        entry.remark,
                        (entry.updated_at or datetime.now(timezone.utc)).isoformat()
                        if entry.updated_at
                        else now,
                        source or entry.source,
                    ),
                )
                count += 1
            db.commit()
        return count

    def get_by_handle(self, handle: str) -> PlayerRosterEntry | None:
        with sqlite3.connect(self._path) as db:
            row = db.execute(
                "SELECT handle, display_name, remark, updated_at, source FROM player_roster WHERE handle = ?",
                (handle,),
            ).fetchone()
        return self._row_to_entry(row)

    def get_by_display_name(self, display_name: str) -> PlayerRosterEntry | None:
        normalized = display_name.strip()
        if not normalized:
            return None
        with sqlite3.connect(self._path) as db:
            row = db.execute(
                """
                SELECT handle, display_name, remark, updated_at, source
                FROM player_roster
                WHERE display_name = ? OR display_name = ?
                LIMIT 2
                """,
                (normalized, display_name),
            ).fetchall()
        if not row:
            return None
        if len(row) > 1:
            return None
        return self._row_to_entry(row[0])

    def get_by_profile_id(self, profile_id: int) -> PlayerRosterEntry | None:
        suffix = f"-{profile_id}"
        with sqlite3.connect(self._path) as db:
            rows = db.execute(
                """
                SELECT handle, display_name, remark, updated_at, source
                FROM player_roster
                WHERE handle LIKE ?
                LIMIT 2
                """,
                (f"%{suffix}",),
            ).fetchall()
        if not rows:
            return None
        if len(rows) > 1:
            return None
        return self._row_to_entry(rows[0])

    def list_all(self) -> list[PlayerRosterEntry]:
        with sqlite3.connect(self._path) as db:
            rows = db.execute(
                """
                SELECT handle, display_name, remark, updated_at, source
                FROM player_roster
                ORDER BY display_name COLLATE NOCASE, handle
                """
            ).fetchall()
        return [entry for row in rows if (entry := self._row_to_entry(row)) is not None]

    def delete(self, handle: str) -> bool:
        with sqlite3.connect(self._path) as db:
            cur = db.execute("DELETE FROM player_roster WHERE handle = ?", (handle,))
            db.commit()
            return cur.rowcount > 0

    def export_rows(self) -> list[dict[str, str]]:
        return [
            {
                "display_name": entry.display_name,
                "handle": entry.handle,
                "remark": entry.remark,
            }
            for entry in self.list_all()
        ]

    @staticmethod
    def _row_to_entry(row: tuple | None) -> PlayerRosterEntry | None:
        if row is None:
            return None
        handle, display_name, remark, updated_at, source = row
        updated: datetime | None = None
        if updated_at:
            try:
                updated = datetime.fromisoformat(str(updated_at))
            except ValueError:
                updated = None
        return PlayerRosterEntry(
            handle=str(handle),
            display_name=str(display_name or ""),
            remark=str(remark or ""),
            updated_at=updated,
            source=str(source or "manual"),
        )
