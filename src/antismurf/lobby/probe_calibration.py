"""Saved calibration profile for Mode 4 — direct address monitoring without rescan."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from antismurf.config.settings import _project_root
from antismurf.lobby.memory_scan_strategies import verify_handle_bytes_at, verify_name_bytes_at
from antismurf.lobby.memory_lobby_roster import OFF_MEMBER_PROFILE_ID
from antismurf.lobby.probe_session_log import format_address, parse_hex_address


@dataclass
class CalibratedProfile:
    expected_handle: str
    expected_name: str
    name_address: int
    handle_address: int
    name_encoding: str = "utf16_le_z"
    handle_encoding: str = "ascii_z"
    struct_base: int | None = None
    name_offset: int | None = None
    handle_offset: int | None = None
    source_mode: str = "manual"
    created_at: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["name_address"] = format_address(self.name_address)
        data["handle_address"] = format_address(self.handle_address)
        if self.struct_base is not None:
            data["struct_base"] = format_address(self.struct_base)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CalibratedProfile:
        return cls(
            expected_handle=str(data["expected_handle"]),
            expected_name=str(data["expected_name"]),
            name_address=int(parse_hex_address(str(data["name_address"])) or 0),
            handle_address=int(parse_hex_address(str(data["handle_address"])) or 0),
            name_encoding=str(data.get("name_encoding", "utf16_le_z")),
            handle_encoding=str(data.get("handle_encoding", "ascii_z")),
            struct_base=parse_hex_address(str(data["struct_base"]))
            if data.get("struct_base")
            else None,
            name_offset=int(data["name_offset"]) if data.get("name_offset") is not None else None,
            handle_offset=int(data["handle_offset"]) if data.get("handle_offset") is not None else None,
            source_mode=str(data.get("source_mode", "manual")),
            created_at=str(data.get("created_at", "")),
            notes=str(data.get("notes", "")),
        )

    def resolved_name_address(self) -> int:
        if self.struct_base is not None and self.name_offset is not None:
            return self.struct_base + self.name_offset
        return self.name_address

    def resolved_handle_address(self) -> int:
        if self.struct_base is not None and self.handle_offset is not None:
            return self.struct_base + self.handle_offset
        return self.handle_address


@dataclass
class LiveFieldReading:
    address: int
    expected: str
    matches: bool
    encoding: str


@dataclass
class LiveProfileReading:
    name: LiveFieldReading
    handle: LiveFieldReading
    all_ok: bool

    def summary_lines(self) -> list[str]:
        flag = "✓" if self.all_ok else "✗"
        lines = [
            f"{flag} 校准读数: 昵称={'OK' if self.name.matches else 'FAIL'} "
            f"句柄={'OK' if self.handle.matches else 'FAIL'}",
            f"  昵称 @ {format_address(self.name.address)} "
            f"期望「{self.name.expected}」",
            f"  句柄 @ {format_address(self.handle.address)} "
            f"期望「{self.handle.expected}」",
        ]
        return lines


def default_profile_path() -> Path:
    root = _project_root()
    return root / "data" / "probe_calibration.json"


def save_profile(profile: CalibratedProfile, path: str | Path | None = None) -> Path:
    target = Path(path) if path else default_profile_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "profile": profile.to_dict()}
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def load_profile(path: str | Path | None = None) -> CalibratedProfile | None:
    target = Path(path) if path else default_profile_path()
    if not target.exists():
        return None
    payload = json.loads(target.read_text(encoding="utf-8"))
    return CalibratedProfile.from_dict(payload["profile"])


def build_profile_from_roster_discovery(
    report: Any,
    *,
    expected_name: str = "",
    notes: str = "",
) -> CalibratedProfile | None:
    if report.best is None:
        return None
    best = report.best
    name_addr = best.record_base + 0x54
    return CalibratedProfile(
        expected_handle=report.host_handle,
        expected_name=expected_name or (best.host_name or ""),
        name_address=name_addr,
        handle_address=best.profile_address,
        name_encoding="utf8_z",
        handle_encoding="profile_triplet",
        struct_base=best.record_base,
        name_offset=0x54,
        handle_offset=OFF_MEMBER_PROFILE_ID,
        source_mode="roster_discovery",
        notes=notes or f"roster members≈{best.member_count}",
    )


def read_profile_live(process_handle, profile: CalibratedProfile) -> LiveProfileReading:
    name_addr = profile.resolved_name_address()
    handle_addr = profile.resolved_handle_address()
    name_ok = verify_name_bytes_at(
        process_handle,
        name_addr,
        profile.expected_name,
        encoding=profile.name_encoding,
    )
    if profile.handle_encoding == "profile_triplet":
        from antismurf.lobby.memory_lobby_roster import verify_lobby_profile_id_at

        handle_ok = verify_lobby_profile_id_at(
            process_handle,
            handle_addr,
            profile.expected_handle,
        )
    else:
        handle_ok = verify_handle_bytes_at(
            process_handle,
            handle_addr,
            profile.expected_handle,
            encoding=profile.handle_encoding,
        )
    reading = LiveProfileReading(
        name=LiveFieldReading(
            address=name_addr,
            expected=profile.expected_name,
            matches=name_ok,
            encoding=profile.name_encoding,
        ),
        handle=LiveFieldReading(
            address=handle_addr,
            expected=profile.expected_handle,
            matches=handle_ok,
            encoding=profile.handle_encoding,
        ),
        all_ok=name_ok and handle_ok,
    )
    return reading


def build_profile_from_trace_report(
    report: Any,
    *,
    notes: str = "",
) -> CalibratedProfile | None:
    names = report.confirmed_names()
    handles = report.confirmed_handles()
    if not names or not handles:
        return None
    best_name = max(names, key=lambda c: c.confirm_score)
    best_handle = max(handles, key=lambda c: c.confirm_score)
    struct_base = None
    name_offset = None
    handle_offset = None
    if report.struct_bases:
        base = report.struct_bases[0]
        struct_base = base.base_address
        name_offset = base.name_offset
        handle_offset = base.handle_offset
    return CalibratedProfile(
        expected_handle=report.expected_handle,
        expected_name=report.expected_name,
        name_address=best_name.address,
        handle_address=best_handle.address,
        name_encoding="utf16_le_z",
        handle_encoding="ascii_z",
        struct_base=struct_base,
        name_offset=name_offset,
        handle_offset=handle_offset,
        source_mode="trace",
        notes=notes or f"trace cycles={report.cycles_completed}",
    )


def build_profile_from_scan_report(report: Any) -> CalibratedProfile | None:
    best = report.best_confirmed()
    if best is not None:
        return CalibratedProfile(
            expected_handle=report.expected_handle,
            expected_name=report.expected_name,
            name_address=best.name_address,
            handle_address=best.handle_address,
            source_mode="scan",
            notes=best.match_source,
        )
    if report.standalone_names and report.standalone_handles:
        return CalibratedProfile(
            expected_handle=report.expected_handle,
            expected_name=report.expected_name,
            name_address=report.standalone_names[0].address,
            handle_address=report.standalone_handles[0].address,
            source_mode="scan_standalone",
            notes="standalone top hits",
        )
    return None
