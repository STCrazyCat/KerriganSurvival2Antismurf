from __future__ import annotations

import sqlite3
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from antismurf.config.settings import _project_root

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_scan_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pid INTEGER NOT NULL,
    scan_mode TEXT NOT NULL,
    duration_ms REAL NOT NULL,
    handles_found INTEGER NOT NULL DEFAULT 0,
    names_found INTEGER NOT NULL DEFAULT 0,
    regions_scanned INTEGER NOT NULL DEFAULT 0,
    fallback_used INTEGER NOT NULL DEFAULT 0,
    scanned_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memory_handle_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    handle TEXT NOT NULL,
    address INTEGER NOT NULL,
    region_base INTEGER NOT NULL,
    region_size INTEGER NOT NULL,
    encoding TEXT NOT NULL,
    FOREIGN KEY(session_id) REFERENCES memory_scan_sessions(id)
);
CREATE INDEX IF NOT EXISTS idx_memory_handle_obs_handle
    ON memory_handle_observations(handle);
CREATE INDEX IF NOT EXISTS idx_memory_handle_obs_region
    ON memory_handle_observations(region_base);
CREATE TABLE IF NOT EXISTS memory_name_bindings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    handle TEXT NOT NULL,
    display_name TEXT NOT NULL,
    name_encoding TEXT NOT NULL,
    handle_address INTEGER NOT NULL,
    name_address INTEGER NOT NULL,
    offset_from_handle INTEGER NOT NULL,
    FOREIGN KEY(session_id) REFERENCES memory_scan_sessions(id)
);
CREATE INDEX IF NOT EXISTS idx_memory_name_bindings_handle
    ON memory_name_bindings(handle);
CREATE TABLE IF NOT EXISTS memory_region_hints (
    region_base INTEGER PRIMARY KEY,
    region_size INTEGER NOT NULL,
    hit_count INTEGER NOT NULL DEFAULT 1,
    last_seen TEXT NOT NULL,
    avg_handles REAL NOT NULL DEFAULT 1.0
);
"""


@dataclass(frozen=True)
class RegionHint:
    region_base: int
    region_size: int
    hit_count: int
    score: float


@dataclass(frozen=True)
class NameOffsetHint:
    offset_from_handle: int
    name_encoding: str
    samples: int


class MemoryProfileStore:
    """Persist memory scan observations for targeted future scans."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        root = _project_root()
        self._path = Path(db_path or root / "data" / "memory_profile.db")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @property
    def db_path(self) -> Path:
        return self._path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            conn.commit()

    def start_session(
        self,
        *,
        pid: int,
        scan_mode: str,
    ) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO memory_scan_sessions
                (pid, scan_mode, duration_ms, handles_found, names_found,
                 regions_scanned, fallback_used, scanned_at)
                VALUES (?, ?, 0, 0, 0, 0, 0, ?)
                """,
                (pid, scan_mode, now),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def finish_session(
        self,
        session_id: int,
        *,
        scan_mode: str,
        duration_ms: float,
        handles_found: int,
        names_found: int,
        regions_scanned: int,
        fallback_used: bool,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE memory_scan_sessions
                SET scan_mode = ?, duration_ms = ?, handles_found = ?, names_found = ?,
                    regions_scanned = ?, fallback_used = ?
                WHERE id = ?
                """,
                (
                    scan_mode,
                    duration_ms,
                    handles_found,
                    names_found,
                    regions_scanned,
                    int(fallback_used),
                    session_id,
                ),
            )
            conn.commit()

    def record_handle_hit(
        self,
        session_id: int,
        *,
        handle: str,
        address: int,
        region_base: int,
        region_size: int,
        encoding: str,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memory_handle_observations
                (session_id, handle, address, region_base, region_size, encoding)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, handle, address, region_base, region_size, encoding),
            )
            conn.execute(
                """
                INSERT INTO memory_region_hints
                (region_base, region_size, hit_count, last_seen, avg_handles)
                VALUES (?, ?, 1, ?, 1.0)
                ON CONFLICT(region_base) DO UPDATE SET
                    region_size = excluded.region_size,
                    hit_count = hit_count + 1,
                    last_seen = excluded.last_seen,
                    avg_handles = (avg_handles * hit_count + 1.0) / (hit_count + 1)
                """,
                (region_base, region_size, now),
            )
            conn.commit()

    def record_name_binding(
        self,
        session_id: int,
        *,
        handle: str,
        display_name: str,
        name_encoding: str,
        handle_address: int,
        name_address: int,
    ) -> None:
        offset = name_address - handle_address
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memory_name_bindings
                (session_id, handle, display_name, name_encoding,
                 handle_address, name_address, offset_from_handle)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    handle,
                    display_name,
                    name_encoding,
                    handle_address,
                    name_address,
                    offset,
                ),
            )
            conn.commit()

    def top_region_hints(self, limit: int = 24) -> list[RegionHint]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT region_base, region_size, hit_count, avg_handles
                FROM memory_region_hints
                ORDER BY hit_count DESC, last_seen DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            RegionHint(
                region_base=int(row["region_base"]),
                region_size=int(row["region_size"]),
                hit_count=int(row["hit_count"]),
                score=float(row["hit_count"]) * float(row["avg_handles"]),
            )
            for row in rows
        ]

    def common_name_offsets(self, limit: int = 8) -> list[NameOffsetHint]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT offset_from_handle, name_encoding, COUNT(*) AS samples
                FROM memory_name_bindings
                GROUP BY offset_from_handle, name_encoding
                HAVING samples >= 2
                ORDER BY samples DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            NameOffsetHint(
                offset_from_handle=int(row["offset_from_handle"]),
                name_encoding=str(row["name_encoding"]),
                samples=int(row["samples"]),
            )
            for row in rows
        ]

    def median_name_offset(self, name_encoding: str | None = None) -> int | None:
        with self._connect() as conn:
            if name_encoding:
                rows = conn.execute(
                    """
                    SELECT offset_from_handle FROM memory_name_bindings
                    WHERE name_encoding = ?
                    """,
                    (name_encoding,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT offset_from_handle FROM memory_name_bindings"
                ).fetchall()
        if len(rows) < 2:
            return None
        values = [int(row["offset_from_handle"]) for row in rows]
        return int(statistics.median(values))

    def preview(self) -> dict:
        with self._connect() as conn:
            sessions = conn.execute(
                "SELECT COUNT(*) FROM memory_scan_sessions"
            ).fetchone()[0]
            hits = conn.execute(
                "SELECT COUNT(*) FROM memory_handle_observations"
            ).fetchone()[0]
            bindings = conn.execute(
                "SELECT COUNT(*) FROM memory_name_bindings"
            ).fetchone()[0]
            regions = conn.execute(
                "SELECT COUNT(*) FROM memory_region_hints"
            ).fetchone()[0]
        return {
            "db_path": str(self._path),
            "sessions": int(sessions),
            "handle_observations": int(hits),
            "name_bindings": int(bindings),
            "region_hints": int(regions),
            "top_regions": [
                {
                    "base": hex(h.region_base),
                    "hits": h.hit_count,
                }
                for h in self.top_region_hints(5)
            ],
        }
