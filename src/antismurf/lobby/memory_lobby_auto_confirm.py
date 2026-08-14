"""Mode 6: automated lobby state confirmation via host anchor + roster struct base.

Workflow:
1. Read local host handle from ``SC2_x64.exe+3E2F340``.
2. Resolve in-room roster ``record_base`` (calibration hint → profile scan → struct scan).
3. Poll roster stride ``0x1B8`` for member handles + UTF-8 nicknames.
4. Emit state transitions: out-of-room / in-room / room-created / member join-leave.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

from antismurf.lobby.memory_host_anchor import read_host_handle_from_process
from antismurf.lobby.memory_lobby_roster import (
    LOBBY_MEMBER_RECORD_SIZE,
    OFF_MEMBER_PROFILE_ID,
    LobbyMemberRecord,
    host_in_roster_at_base,
    read_roster_members_at_base,
    scan_lobby_struct_rosters,
    scan_process_for_lobby_profile_handle,
    verify_lobby_member_record_at,
)
from antismurf.lobby.probe_calibration import CalibratedProfile


class LobbyPhase(str, Enum):
    UNKNOWN = "unknown"
    OUT_OF_ROOM = "out_of_room"
    IN_ROOM = "in_room"


class RoomPresenceDebouncer:
    """Hysteresis for in-room detection to absorb transient memory read misses."""

    def __init__(self, *, enter_required: int = 2, exit_required: int = 4) -> None:
        self.enter_required = max(1, enter_required)
        self.exit_required = max(1, exit_required)
        self._confirmed = False
        self._in_streak = 0
        self._out_streak = 0

    @property
    def confirmed_in_room(self) -> bool:
        return self._confirmed

    @property
    def in_streak(self) -> int:
        return self._in_streak

    @property
    def out_streak(self) -> int:
        return self._out_streak

    def update(self, raw_in_room: bool) -> bool:
        if raw_in_room:
            self._in_streak += 1
            self._out_streak = 0
            if not self._confirmed and self._in_streak >= self.enter_required:
                self._confirmed = True
        else:
            self._out_streak += 1
            self._in_streak = 0
            if self._confirmed and self._out_streak >= self.exit_required:
                self._confirmed = False
                self._out_streak = 0
        return self._confirmed


@dataclass(frozen=True)
class LobbyMemberView:
    slot: int
    handle: str
    display_name: str
    record_base: int
    profile_address: int
    team_name: str = ""
    raw_display_name: str = ""
    is_host: bool = False

    @classmethod
    def from_record(cls, index: int, record: LobbyMemberRecord, *, host_handle: str) -> LobbyMemberView:
        return cls(
            slot=index,
            handle=record.handle,
            display_name=record.display_name or "?",
            team_name=record.team_name or "",
            raw_display_name=record.raw_display_name or record.display_name or "",
            record_base=record.record_base,
            profile_address=record.profile_address,
            is_host=record.handle == host_handle,
        )

    def summary_line(self) -> str:
        tag = " [主机]" if self.is_host else ""
        team = f"<{self.team_name}> " if self.team_name else ""
        return (
            f"  [{self.slot + 1}] {self.handle} {team}\"{self.display_name}\" "
            f"@0x{self.record_base:X}{tag}"
        )


@dataclass
class LobbyAutoConfirmSnapshot:
    tick: int
    timestamp: float
    host_handle: str
    host_anchor_ok: bool
    host_name: str | None = None
    record_base: int | None = None
    record_base_source: str = "none"
    phase: LobbyPhase = LobbyPhase.UNKNOWN
    in_room: bool = False
    raw_in_room: bool = False
    room_created: bool = False
    member_count: int = 0
    members: list[LobbyMemberView] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    # 句柄位置确认状态:确认当前是否抓到房间内玩家句柄
    handle_location_state: str = "unknown"  # confirmed / unconfirmed
    handle_location_source: str = "none"    # anchor / sniff / accounts / roster
    host_handle_address: int | None = None
    host_handle_encoding: str | None = None
    roster_verified: bool = False

    def headline(self) -> str:
        base = f"0x{self.record_base:X}" if self.record_base is not None else "-"
        return (
            f"#{self.tick} 主机={self.host_handle}  阶段={self.phase.value}  "
            f"基址={base}({self.record_base_source})  成员={self.member_count}  "
            f"已创建房间={'是' if self.room_created else '否'}"
        )

    def member_lines(self) -> list[str]:
        return [member.summary_line() for member in self.members]


@dataclass
class LobbyAutoConfirmReport:
    host_handle: str
    snapshots: list[LobbyAutoConfirmSnapshot] = field(default_factory=list)
    events: list[str] = field(default_factory=list)

    def summary_lines(self) -> list[str]:
        lines = [
            "=== 模式6 自动化房间确认报告 ===",
            f"主机句柄: {self.host_handle}",
            f"采样次数: {len(self.snapshots)}",
            f"状态事件: {len(self.events)}",
        ]
        if self.events:
            lines.append("--- 事件 ---")
            lines.extend(f"  {event}" for event in self.events[-20:])
        if self.snapshots:
            last = self.snapshots[-1]
            lines.append("--- 最新状态 ---")
            lines.append(f"  {last.headline()}")
            lines.extend(last.member_lines())
        return lines


def resolve_record_base(
    process_handle,
    host_handle: str,
    *,
    calibration: CalibratedProfile | None = None,
    rescan_budget_sec: float = 4.0,
) -> tuple[int | None, str]:
    """Find roster record base (calibration hint → profile scan → struct scan)."""
    if calibration is not None and calibration.struct_base is not None:
        base = calibration.struct_base
        handle_ok = (
            not calibration.expected_handle
            or calibration.expected_handle == host_handle
        )
        if handle_ok and host_in_roster_at_base(process_handle, base, host_handle):
            return base, "calibration"

    hits = scan_process_for_lobby_profile_handle(
        process_handle,
        host_handle,
        time_budget_sec=rescan_budget_sec,
    )
    best_base: int | None = None
    best_members = 0
    for profile_addr in hits:
        base = profile_addr - OFF_MEMBER_PROFILE_ID
        if not verify_lobby_member_record_at(process_handle, base, host_handle):
            continue
        members = read_roster_members_at_base(process_handle, base)
        if not any(item.handle == host_handle for _slot, item in members):
            continue
        if len(members) > best_members:
            best_members = len(members)
            best_base = base
    if best_base is not None:
        return best_base, "profile_scan"

    clusters = scan_lobby_struct_rosters(
        process_handle,
        known_handles={host_handle},
        min_members=1,
        time_budget_sec=rescan_budget_sec,
    )
    clusters.sort(key=lambda item: item.score, reverse=True)
    for cluster in clusters:
        for profile_addr, handle in cluster.members:
            if handle != host_handle:
                continue
            base = profile_addr - OFF_MEMBER_PROFILE_ID
            if verify_lobby_member_record_at(process_handle, base, host_handle):
                return base, "struct_scan"

    return None, "none"


def evaluate_lobby_snapshot(
    *,
    host_handle: str,
    record_base: int | None,
    members: list[LobbyMemberRecord] | list[tuple[int, LobbyMemberRecord]],
) -> tuple[LobbyPhase, bool, bool]:
    """Return phase, in_room, room_created."""
    if record_base is None or not members:
        return LobbyPhase.OUT_OF_ROOM, False, False

    if isinstance(members[0], tuple):
        occupied: list[tuple[int, LobbyMemberRecord]] = members  # type: ignore[assignment]
    else:
        occupied = [(index, item) for index, item in enumerate(members)]  # type: ignore[arg-type]

    host_slots = [slot for slot, item in occupied if item.handle == host_handle]
    if not host_slots:
        return LobbyPhase.OUT_OF_ROOM, False, False

    room_created = min(host_slots) == 0
    return LobbyPhase.IN_ROOM, True, room_created


class LobbyAutoConfirmSession:
    """Mode 6 polling session."""

    def __init__(
        self,
        process_handle,
        *,
        pid: int,
        host_handle_module_offset: int | str = 0x3E2F340,
        calibration: CalibratedProfile | None = None,
        rescan_budget_sec: float = 4.0,
        rescan_every_ticks: int = 15,
        fallback_host_handle: str = "",
        enter_confirm_ticks: int = 2,
        exit_confirm_ticks: int = 4,
        sniff_enabled: bool = True,
        sniff_radius: int = 8192,
        calibration_path: str | None = None,
    ) -> None:
        self._process = process_handle
        self._pid = pid
        self._host_offset = host_handle_module_offset
        self._calibration = calibration
        self._fallback_host_handle = fallback_host_handle.strip()
        self._rescan_budget_sec = rescan_budget_sec
        self._rescan_every_ticks = max(1, rescan_every_ticks)
        self._default_rescan_every_ticks = self._rescan_every_ticks
        self._sniff_enabled = sniff_enabled
        self._sniff_radius = sniff_radius
        self._calibration_path = calibration_path
        self._presence = RoomPresenceDebouncer(
            enter_required=enter_confirm_ticks,
            exit_required=exit_confirm_ticks,
        )
        self.started_at = time.time()
        self._tick = 0
        self._cached_base: int | None = None
        self._cached_source = "none"
        self._last_good_members: list[tuple[int, LobbyMemberRecord]] = []
        self._last_member_keys: tuple[tuple[str, str], ...] = ()
        self._last_phase = LobbyPhase.UNKNOWN
        # 句柄位置确认状态
        self._handle_location_state = "unknown"
        self._handle_location_source = "none"
        self._host_handle_address: int | None = None
        self._host_handle_encoding: str | None = None
        self._sniffed_offset: int | None = None
        self.snapshots: list[LobbyAutoConfirmSnapshot] = []
        self.events: list[str] = []

    def _read_host(self) -> tuple[str | None, bool, str | None]:
        anchor = read_host_handle_from_process(
            self._process,
            pid=self._pid,
            offset=self._host_offset,
        )
        if anchor is not None:
            self._mark_host_confirmed(
                anchor.handle,
                getattr(anchor, "handle_address", None),
                getattr(anchor, "encoding", ""),
                "anchor",
            )
            host_name: str | None = None
            if self._calibration and self._calibration.expected_handle == anchor.handle:
                host_name = self._calibration.expected_name or None
            return anchor.handle, True, host_name

        # 固定跳转失效 → 在主机句柄附近嗅探(多格式存储 + 附近信息解读)
        if self._sniff_enabled:
            candidate = self._sniff_host()
            if candidate is not None:
                self._mark_host_confirmed(
                    candidate.handle,
                    candidate.address,
                    candidate.encoding,
                    "sniff",
                )
                logger.info(
                    "主机句柄经嗅探确认: %s @ 0x%X (%s)",
                    candidate.handle,
                    candidate.address,
                    candidate.encoding,
                )
                return candidate.handle, True, None

        from antismurf.lobby.memory_reader import detect_local_handle

        detected = detect_local_handle(
            self._process,
            pid=self._pid,
            host_anchor_offset=self._host_offset,
        )
        if detected:
            self._handle_location_state = "unconfirmed"
            self._handle_location_source = "accounts"
            self._host_handle_address = None
            return detected, True, None

        if self._fallback_host_handle:
            from antismurf.models.player import is_valid_handle

            if is_valid_handle(self._fallback_host_handle):
                self._handle_location_state = "unconfirmed"
                self._handle_location_source = "fallback"
                return self._fallback_host_handle, False, None

        self._handle_location_state = "unconfirmed"
        self._handle_location_source = "none"
        self._host_handle_address = None
        return None, False, None

    def _mark_host_confirmed(self, handle: str, address: int, encoding: str, source: str) -> None:
        self._handle_location_state = "confirmed"
        self._handle_location_source = source
        self._host_handle_address = address
        self._host_handle_encoding = encoding

    def _sniff_host(self):
        from antismurf.lobby.memory_host_anchor import (
            confirm_host_handle_via_sniff,
        )
        from antismurf.lobby.memory_probe import build_module_map

        try:
            modules = build_module_map(self._pid)
        except Exception as exc:  # noqa: BLE001
            logger.warning("build_module_map failed: %s", exc)
            return None
        candidate = confirm_host_handle_via_sniff(
            self._process,
            modules,
            anchor_offset=self._host_offset,
            radius=self._sniff_radius,
            min_score=60.0,
        )
        if candidate is None:
            return None
        module = next(
            (m for m in modules if str(getattr(m, "name", "")).lower().startswith("sc2")),
            None,
        )
        if module is not None:
            offset = candidate.address - int(module.base)
            if 0 <= offset < int(module.size) and offset != self._sniffed_offset:
                self._sniffed_offset = offset
                self._persist_sniffed_offset(offset, candidate.handle)
        return candidate

    def _persist_sniffed_offset(self, offset: int, handle: str) -> None:
        try:
            from antismurf.lobby.probe_calibration import update_host_handle_offset

            update_host_handle_offset(
                offset,
                self._calibration_path,
                expected_handle=handle,
                notes="嗅探确认的主机句柄模块偏移(随版本自动更新)",
            )
            logger.info("已保存嗅探确认的主机句柄偏移 0x%X", offset)
        except Exception as exc:  # noqa: BLE001
            logger.warning("保存嗅探偏移失败: %s", exc)

    def _reconfirm_handle_location(self, force: bool) -> None:
        """force 时重新确认句柄位置:即使锚点可读也用嗅探复核。"""
        if not force or not self._sniff_enabled:
            return
        if self._handle_location_state == "unconfirmed":
            return
        candidate = self._sniff_host()
        if candidate is not None and candidate.address != self._host_handle_address:
            self._mark_host_confirmed(
                candidate.handle, candidate.address, candidate.encoding, "sniff"
            )
            logger.info(
                "手动刷新:句柄位置更新为 0x%X (%s)",
                candidate.address,
                candidate.encoding,
            )

    def _resolve_base(self, host_handle: str, *, force_rescan: bool) -> tuple[int | None, str]:
        if self._cached_base is not None:
            if host_in_roster_at_base(self._process, self._cached_base, host_handle):
                return self._cached_base, self._cached_source
            if self._presence.confirmed_in_room and self._presence.out_streak < self._presence.exit_required:
                return self._cached_base, self._cached_source
            if not force_rescan:
                return self._cached_base, self._cached_source

        base, source = resolve_record_base(
            self._process,
            host_handle,
            calibration=self._calibration,
            rescan_budget_sec=self._rescan_budget_sec,
        )
        if base is not None:
            self._cached_base = base
            self._cached_source = source
        elif not self._presence.confirmed_in_room:
            self._cached_base = None
            self._cached_source = "none"
        return self._cached_base, self._cached_source if self._cached_base is not None else "none"

    def _should_rescan(self, host_handle: str, *, force_rescan: bool) -> bool:
        if force_rescan:
            return True
        if self._tick == 1:
            return True
        if self._presence.confirmed_in_room and self._cached_base is not None:
            if host_in_roster_at_base(self._process, self._cached_base, host_handle):
                return False
            return self._presence.out_streak >= self._presence.exit_required
        return self._tick % self._rescan_every_ticks == 0

    def _emit_events(
        self,
        snapshot: LobbyAutoConfirmSnapshot,
        member_keys: tuple[tuple[str, str], ...],
    ) -> None:
        if self._last_phase != snapshot.phase:
            if snapshot.phase == LobbyPhase.IN_ROOM:
                self.events.append(
                    f"已进入房间: roster 基址 0x{snapshot.record_base:X} "
                    f"({snapshot.record_base_source})"
                )
            elif self._last_phase == LobbyPhase.IN_ROOM:
                self.events.append("已退出房间: roster 块不可读或主机不在列表")

        if snapshot.phase == LobbyPhase.IN_ROOM and snapshot.room_created and self._last_phase != LobbyPhase.IN_ROOM:
            self.events.append(f"已创建房间（主机 {snapshot.host_handle} 在 roster[0]）")

        if snapshot.phase == LobbyPhase.IN_ROOM and member_keys != self._last_member_keys:
            old = {key for key in self._last_member_keys}
            new = {key for key in member_keys}
            for handle, name in sorted(new - old):
                self.events.append(f"玩家加入: {handle} \"{name}\"")
            for handle, name in sorted(old - new):
                self.events.append(f"玩家离开: {handle} \"{name}\"")

        self._last_phase = snapshot.phase
        self._last_member_keys = member_keys

    def set_rescan_every_ticks(self, every: int) -> None:
        self._rescan_every_ticks = max(1, every)

    def tick(self, *, force_rescan: bool = False) -> LobbyAutoConfirmSnapshot:
        self._tick += 1
        host_handle, anchor_ok, host_name = self._read_host()
        notes: list[str] = []
        if host_handle is None:
            snapshot = LobbyAutoConfirmSnapshot(
                tick=self._tick,
                timestamp=time.time(),
                host_handle="?",
                host_anchor_ok=False,
                phase=LobbyPhase.UNKNOWN,
                notes=["未能读取主机锚点句柄"],
                handle_location_state=self._handle_location_state,
                handle_location_source=self._handle_location_source,
            )
            self.snapshots.append(snapshot)
            return snapshot

        if force_rescan:
            self._reconfirm_handle_location(True)

        should_rescan = self._should_rescan(host_handle, force_rescan=force_rescan)
        record_base, source = self._resolve_base(host_handle, force_rescan=should_rescan)
        members_raw: list[tuple[int, LobbyMemberRecord]] = []
        if record_base is not None:
            members_raw = read_roster_members_at_base(self._process, record_base)
        if record_base is None:
            notes.append("未解析到 roster 基址（可能未创建房间或已退房）")
        elif source == "calibration":
            notes.append("使用校准 struct 基址")
        elif source == "profile_scan":
            notes.append("通过主机 profile 扫描定位基址")

        raw_phase, raw_in_room, room_created = evaluate_lobby_snapshot(
            host_handle=host_handle,
            record_base=record_base,
            members=members_raw,
        )
        roster_verified = bool(
            record_base is not None
            and any(item.handle == host_handle for _slot, item in members_raw)
        )
        if roster_verified:
            self._handle_location_state = "confirmed"
            self._handle_location_source = "roster"
        if raw_in_room and members_raw:
            self._last_good_members = list(members_raw)

        display_members = members_raw
        if (
            self._presence.confirmed_in_room
            and not raw_in_room
            and self._last_good_members
        ):
            display_members = list(self._last_good_members)
            notes.append("读抖帧，沿用上一帧成员")

        was_confirmed = self._presence.confirmed_in_room
        confirmed_in_room = self._presence.update(raw_in_room)
        if was_confirmed and not confirmed_in_room:
            self._cached_base = None
            self._cached_source = "none"
            self._last_good_members = []
            display_members = members_raw

        if confirmed_in_room:
            phase = LobbyPhase.IN_ROOM
            in_room = True
        elif raw_in_room and self._presence.in_streak > 0:
            phase = LobbyPhase.UNKNOWN
            in_room = False
        else:
            phase = LobbyPhase.OUT_OF_ROOM
            in_room = False

        members = [
            LobbyMemberView.from_record(slot_index, record, host_handle=host_handle)
            for slot_index, record in display_members
        ]
        snapshot = LobbyAutoConfirmSnapshot(
            tick=self._tick,
            timestamp=time.time(),
            host_handle=host_handle,
            host_anchor_ok=anchor_ok,
            host_name=host_name,
            record_base=record_base,
            record_base_source=source,
            phase=phase,
            in_room=in_room,
            raw_in_room=raw_in_room,
            room_created=room_created if in_room else False,
            member_count=len(members),
            members=members,
            notes=notes,
            handle_location_state=self._handle_location_state,
            handle_location_source=self._handle_location_source,
            host_handle_address=self._host_handle_address,
            host_handle_encoding=self._host_handle_encoding,
            roster_verified=roster_verified,
        )
        member_keys = tuple((item.handle, item.display_name) for item in members)
        self._emit_events(snapshot, member_keys)
        self.snapshots.append(snapshot)
        return snapshot

    def build_report(self) -> LobbyAutoConfirmReport:
        host = self.snapshots[-1].host_handle if self.snapshots else "?"
        return LobbyAutoConfirmReport(
            host_handle=host,
            snapshots=list(self.snapshots),
            events=list(self.events),
        )
