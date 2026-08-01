"""Mode 3: CE-style trace monitor — enter/leave filtering + struct base / pointer roots.

Workflow (mirrors Cheat Engine "first scan → next scan → pointer scan"):
1. Initial scan for handle + nickname byte occurrences.
2. User toggles target player in/out of the lobby repeatedly.
3. Filter addresses that appear in-room and vanish (or go stale) out-of-room.
4. Poll watched addresses for byte-level writes between ticks.
5. Infer struct base from confirmed field addresses; trace pointer roots iteratively
   (BFS with visited set — no recursive pointer chasing).
"""

from __future__ import annotations

import hashlib
import struct
import time
from dataclasses import dataclass, field
from enum import Enum

from antismurf.lobby.memory_host_anchor import (
    HostHandleAnchor,
    read_host_handle_anchor,
    scan_module_vicinity_handles,
)
from antismurf.lobby.memory_probe import (
    StandaloneHit,
    _boost_standalone_with_host_anchor,
    _build_standalone_hits,
    _score_handle_location,
    _seed_handle_hits_from_host_anchor,
    build_module_map,
    locate_address,
    make_scan_bytes_fn,
    score_name_probe,
    NameProbeResult,
)
from antismurf.lobby.memory_scan_strategies import (
    DEFAULT_SCAN_STRATEGIES,
    ScanStrategies,
    scan_process_for_decoded_handles,
    scan_process_for_decoded_strings,
    verify_handle_bytes_at,
    verify_name_bytes_at,
)
from antismurf.lobby.memory_channel_roster import (
    ChannelRosterSnapshot,
    pick_handle_address_in_cluster,
    pick_name_in_roster_window,
    roster_delta,
    scan_channel_rosters,
)
from antismurf.lobby.memory_reader import _iter_readable_regions_typed, _read_memory


class RoomPhase(str, Enum):
    OUT = "out_room"
    IN = "in_room"


@dataclass
class TraceCandidate:
    """One watched address under enter/leave + write monitoring."""

    kind: str  # "name" | "handle"
    address: int
    region_type: str
    module_label: str
    lobby_score: float
    strategy: str = ""
    seen_in_room: int = 0
    seen_out_room: int = 0
    absent_after_leave: int = 0
    present_after_enter: int = 0
    write_events: int = 0
    last_bytes_hash: str = ""
    last_change_at: float = 0.0
    confirmed: bool = False
    confirm_score: float = 0.0
    in_channel_roster: bool = False
    channel_roster_members: int = 0
    notes: list[str] = field(default_factory=list)

    def summary_line(self) -> str:
        flag = "★" if self.confirmed else "·"
        return (
            f"{flag} [{self.kind}] 0x{self.address:X} ({self.module_label}, {self.region_type}) "
            f"分={self.confirm_score:.0f} 进房={self.seen_in_room} 离房={self.seen_out_room} "
            f"写入={self.write_events} | {'; '.join(self.notes[:2])}"
        )


@dataclass(frozen=True)
class StructBaseCandidate:
    base_address: int
    name_offset: int | None
    handle_offset: int | None
    region_type: str
    confidence: float
    notes: list[str]

    def summary_line(self) -> str:
        parts = [f"基址 0x{self.base_address:X} ({self.region_type}) 置信 {self.confidence:.0f}"]
        if self.name_offset is not None:
            parts.append(f"name+{self.name_offset}")
        if self.handle_offset is not None:
            parts.append(f"handle+{self.handle_offset}")
        return " | ".join(parts) + " | " + "; ".join(self.notes[:2])


@dataclass(frozen=True)
class PointerChain:
    """Static or heap root → … → field (built iteratively, acyclic)."""

    field_address: int
    root_address: int
    chain: tuple[int, ...]
    depth: int
    root_module: str | None
    notes: str

    def summary_line(self) -> str:
        chain_text = " → ".join(f"0x{addr:X}" for addr in self.chain)
        mod = self.root_module or "heap"
        return f"[depth {self.depth}] {chain_text} ({mod}) {self.notes}"


@dataclass
class TraceMonitorTick:
    phase: RoomPhase
    cycle: int
    message: str
    scan_name_count: int = 0
    scan_handle_count: int = 0
    write_events: list[tuple[str, int]] = field(default_factory=list)
    newly_confirmed: list[TraceCandidate] = field(default_factory=list)


@dataclass
class TraceMonitorReport:
    expected_name: str
    expected_handle: str
    candidates: list[TraceCandidate] = field(default_factory=list)
    struct_bases: list[StructBaseCandidate] = field(default_factory=list)
    pointer_chains: list[PointerChain] = field(default_factory=list)
    cycles_completed: int = 0
    channel_rosters: list = field(default_factory=list)

    def confirmed_names(self) -> list[TraceCandidate]:
        return [c for c in self.candidates if c.confirmed and c.kind == "name"]

    def confirmed_handles(self) -> list[TraceCandidate]:
        return [c for c in self.candidates if c.confirmed and c.kind == "handle"]

    def summary_lines(self) -> list[str]:
        lines = [
            f"=== 模式3 追踪报告 ===",
            f"目标: {self.expected_name} / {self.expected_handle}",
            f"进出循环: {self.cycles_completed} 次",
            f"候选: {len(self.candidates)}  确认昵称: {len(self.confirmed_names())}  "
            f"确认句柄: {len(self.confirmed_handles())}",
        ]
        confirmed = [c for c in self.candidates if c.confirmed]
        if confirmed:
            lines.append("--- 已确认地址 ---")
            for item in sorted(confirmed, key=lambda c: c.confirm_score, reverse=True)[:12]:
                lines.append(item.summary_line())
        if self.struct_bases:
            lines.append("--- 结构体基址推测 ---")
            for base in self.struct_bases[:5]:
                lines.append(f"  {base.summary_line()}")
        if self.pointer_chains:
            lines.append("--- 指针链 (溯源) ---")
            for chain in self.pointer_chains[:8]:
                lines.append(f"  {chain.summary_line()}")
        if self.channel_rosters:
            lines.append("--- 房间频道 roster ---")
            for cluster in self.channel_rosters[:6]:
                lines.append(f"  {cluster.summary_line()}")
        return lines


def _bytes_hash(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()[:12]


def _read_field_bytes(
    process_handle,
    address: int,
    kind: str,
    expected_name: str,
    expected_handle: str,
) -> bytes:
    if kind == "name":
        size = len(expected_name.encode("utf-16-le")) + 8
    else:
        size = len(expected_handle.encode("ascii")) + 4
    return _read_memory(process_handle, address, max(32, size)) or b""


def _still_matches(
    process_handle,
    address: int,
    kind: str,
    expected_name: str,
    expected_handle: str,
) -> bool:
    if kind == "name":
        return verify_name_bytes_at(
            process_handle,
            address,
            expected_name,
            encoding="utf16_le_z",
        )
    return verify_handle_bytes_at(
        process_handle,
        address,
        expected_handle,
        encoding="ascii_z",
    )


def _candidate_key(kind: str, address: int) -> tuple[str, int]:
    return kind, address


def compute_confirm_score(candidate: TraceCandidate) -> float:
    """Higher = more likely live lobby row for the target player."""
    score = candidate.lobby_score * 0.3
    if candidate.region_type == "private":
        score += 25.0
    elif candidate.region_type == "mapped":
        score += 10.0
    elif candidate.region_type == "image":
        score -= 35.0

    in_only = max(0, candidate.seen_in_room - candidate.seen_out_room)
    score += in_only * 8.0
    score += candidate.present_after_enter * 10.0
    score += candidate.absent_after_leave * 10.0
    score += min(candidate.write_events, 5) * 4.0

    if candidate.seen_out_room > 0 and candidate.seen_in_room > 0:
        ratio = candidate.seen_in_room / max(candidate.seen_out_room, 1)
        if ratio >= 1.5:
            score += 15.0

    if candidate.in_channel_roster:
        score += 35.0
        score += max(0, candidate.channel_roster_members - 1) * 8.0

    static_penalty = candidate.seen_out_room >= 2 and candidate.seen_in_room >= 2
    if static_penalty and candidate.region_type == "image":
        score -= 40.0

    return score


def is_confirmed_candidate(candidate: TraceCandidate, *, min_cycles: int = 1) -> bool:
    score = compute_confirm_score(candidate)
    candidate.confirm_score = score
    toggled = candidate.present_after_enter >= 1 and candidate.absent_after_leave >= 1
    in_room_bias = candidate.seen_in_room >= 1 and (
        candidate.seen_in_room > candidate.seen_out_room
        or candidate.write_events >= 1
    )
    not_static_ui = not (
        candidate.region_type == "image"
        and candidate.seen_out_room >= 2
        and candidate.absent_after_leave == 0
    )
    candidate.confirmed = (
        score >= 45.0
        and toggled
        and in_room_bias
        and not_static_ui
        and (candidate.present_after_enter + candidate.absent_after_leave) >= min_cycles
    )
    if candidate.confirmed:
        candidate.notes.append(f"confirmed score={score:.0f}")
    return candidate.confirmed


def infer_struct_bases(
    name_addrs: list[int],
    handle_addrs: list[int],
    *,
    region_types: dict[int, str],
) -> list[StructBaseCandidate]:
    if not name_addrs and not handle_addrs:
        return []

    results: list[StructBaseCandidate] = []

    def _add_base(
        base: int,
        name_off: int | None,
        handle_off: int | None,
        *,
        region: str,
        confidence: float,
        notes: list[str],
    ) -> None:
        results.append(
            StructBaseCandidate(
                base_address=base,
                name_offset=name_off,
                handle_offset=handle_off,
                region_type=region,
                confidence=confidence,
                notes=notes,
            )
        )

    for name_addr in name_addrs[:3]:
        for handle_addr in handle_addrs[:3]:
            low = min(name_addr, handle_addr)
            distance = abs(handle_addr - name_addr)
            if distance <= 8192:
                for align in (0x1000, 0x200, 0x100, 0x80, 0x40, 0x20, 0x10):
                    base = low & ~(align - 1)
                    if base > low:
                        continue
                    n_off = name_addr - base
                    h_off = handle_addr - base
                    if n_off > 8192 or h_off > 8192:
                        continue
                    region = region_types.get(base, region_types.get(name_addr, "unknown"))
                    confidence = 60.0 + (25.0 if region == "private" else 0.0)
                    if distance < 256:
                        confidence += 20.0
                    elif distance < 768:
                        confidence += 10.0
                    _add_base(
                        base,
                        n_off,
                        h_off,
                        region=region,
                        confidence=confidence,
                        notes=[f"对齐 0x{align:X}", f"字段相距 {distance} 字节"],
                    )
                    break
            else:
                region_n = region_types.get(name_addr, "unknown")
                region_h = region_types.get(handle_addr, "unknown")
                for addr, kind, region in (
                    (name_addr, "name", region_n),
                    (handle_addr, "handle", region_h),
                ):
                    for align in (0x100, 0x40, 0x20, 0x10):
                        base = addr & ~(align - 1)
                        off = addr - base
                        if off > 512:
                            continue
                        conf = 50.0 + (20.0 if region == "private" else 0.0)
                        notes = [
                            f"远程字段 {kind}",
                            f"与配对字段相距 {distance} 字节",
                        ]
                        if kind == "name":
                            _add_base(base, off, None, region=region, confidence=conf, notes=notes)
                        else:
                            _add_base(base, None, off, region=region, confidence=conf, notes=notes)
                        break

    results.sort(key=lambda item: item.confidence, reverse=True)
    deduped: list[StructBaseCandidate] = []
    seen_bases: set[int] = set()
    for item in results:
        if item.base_address in seen_bases:
            continue
        seen_bases.add(item.base_address)
        deduped.append(item)
    return deduped


def _find_pointers_in_window(
    data: bytes,
    window_base: int,
    target: int,
    *,
    slack: int = 0x40,
) -> list[int]:
    refs: list[int] = []
    lo = max(0, target - slack)
    hi = target + slack
    for offset in range(0, len(data) - 7, 8):
        value = struct.unpack_from("<Q", data, offset)[0]
        if lo <= value <= hi:
            refs.append(window_base + offset)
    return refs


def trace_pointer_roots_iterative(
    process_handle,
    field_address: int,
    modules: list,
    *,
    max_depth: int = 3,
    max_chains: int = 8,
    search_back_bytes: int = 4096,
) -> list[PointerChain]:
    """BFS pointer scan with visited set — avoids recursive cycles."""
    chains: list[PointerChain] = []
    visited_targets: set[int] = set()
    # frontier: (current_field, chain_from_root_to_field)
    frontier: list[tuple[int, tuple[int, ...]]] = [(field_address, (field_address,))]

    for depth in range(1, max_depth + 1):
        next_frontier: list[tuple[int, tuple[int, ...]]] = []
        for target, chain in frontier:
            if target in visited_targets:
                continue
            visited_targets.add(target)

            location = locate_address(
                target,
                modules=modules,
                process_handle=process_handle,
            )
            region_base = location.region_base
            region_size = min(location.region_size, 8 * 1024 * 1024)
            scan_start = max(region_base, target - search_back_bytes)
            scan_end = min(region_base + region_size, target + 512)
            scan_size = scan_end - scan_start
            if scan_size <= 0:
                continue
            data = _read_memory(process_handle, scan_start, scan_size) or b""
            refs = _find_pointers_in_window(data, scan_start, target)

            for ref in refs:
                if ref in chain:
                    continue
                new_chain = (ref,) + chain
                ref_loc = locate_address(
                    ref,
                    modules=modules,
                    process_handle=process_handle,
                )
                if ref_loc.region_type == "image" and ref_loc.module_name:
                    chains.append(
                        PointerChain(
                            field_address=field_address,
                            root_address=ref,
                            chain=new_chain,
                            depth=depth,
                            root_module=ref_loc.module_label,
                            notes="static/module root",
                        )
                    )
                    if len(chains) >= max_chains:
                        return chains
                elif ref not in visited_targets:
                    next_frontier.append((ref, new_chain))

        frontier = next_frontier
        if not frontier:
            break

    return chains


class TraceMonitorSession:
    """Mode 3: continuous enter/leave monitoring with CE-style narrowing."""

    def __init__(
        self,
        process_handle,
        *,
        pid: int,
        expected_handle: str,
        expected_name: str,
        strategies: ScanStrategies | None = None,
        max_candidates: int = 40,
        rescan_every_ticks: int = 4,
        room_member_handles: set[str] | None = None,
    ) -> None:
        self._process = process_handle
        self._pid = pid
        self.expected_handle = expected_handle.strip()
        self.expected_name = expected_name.strip()
        self.strategies = strategies or DEFAULT_SCAN_STRATEGIES
        self.max_candidates = max_candidates
        self.rescan_every_ticks = rescan_every_ticks
        self._room_handles: set[str] = set(room_member_handles or set())
        self._room_handles.add(self.expected_handle)
        self._roster_baseline: ChannelRosterSnapshot | None = None
        self._roster_current: ChannelRosterSnapshot | None = None
        self._active_rosters: list = []

        self.phase = RoomPhase.OUT
        self.cycle = 0
        self._tick_count = 0
        self._candidates: dict[tuple[str, int], TraceCandidate] = {}
        self._last_scan_names: set[int] = set()
        self._last_scan_handles: set[int] = set()
        self._modules: list = []
        self._host_anchor: HostHandleAnchor | None = None
        self.events: list[TraceMonitorTick] = []
        self._initialized = False

    def _bootstrap_host_anchor(self) -> None:
        if not self.strategies.use_host_anchor:
            self._host_anchor = None
            return
        if not self._modules:
            self._modules = build_module_map(self._pid)
        self._host_anchor = read_host_handle_anchor(
            self._process,
            self._modules,
            offset=self.strategies.host_handle_module_offset,
        )
        if self._host_anchor is None:
            return
        self._room_handles.add(self._host_anchor.handle)
        for vhit in scan_module_vicinity_handles(
            self._process,
            self._host_anchor,
            self._modules,
            radius=self.strategies.host_anchor_scan_radius,
        ):
            self._room_handles.add(vhit.handle)

    def _scan_addresses(self) -> tuple[set[int], set[int]]:
        scan_fn = make_scan_bytes_fn(self.strategies)
        name_hits = scan_process_for_decoded_strings(
            self._process,
            self.expected_name,
            scan_fn,
            strategies=self.strategies,
            time_budget_sec=10.0,
            max_hits=self.max_candidates,
        )
        handle_hits = scan_process_for_decoded_handles(
            self._process,
            self.expected_handle,
            scan_fn,
            strategies=self.strategies,
            time_budget_sec=10.0,
            max_hits=self.max_candidates,
        )
        return {item.address for item in name_hits}, {item.address for item in handle_hits}

    def _scan_room_channel_rosters(self, phase: RoomPhase) -> ChannelRosterSnapshot:
        if not self.strategies.use_channel_roster:
            snapshot = ChannelRosterSnapshot(timestamp=time.time(), phase=phase.value, clusters=[])
            self._roster_current = snapshot
            return snapshot
        clusters = scan_channel_rosters(
            self._process,
            known_handles=self._room_handles,
            min_members=self.strategies.channel_roster_min_members,
            max_span=self.strategies.channel_roster_max_span,
            time_budget_sec=6.0,
            prefer_private=True,
            use_lobby_member_struct=self.strategies.use_lobby_member_struct,
            lobby_member_max_slots=self.strategies.lobby_member_max_slots,
        )
        snapshot = ChannelRosterSnapshot(
            timestamp=time.time(),
            phase=phase.value,
            clusters=clusters,
        )
        self._roster_current = snapshot
        if phase == RoomPhase.OUT and self._roster_baseline is None:
            self._roster_baseline = snapshot
        if phase == RoomPhase.IN:
            new_clusters, new_handles = roster_delta(snapshot, self._roster_baseline)
            target_rosters = [
                cluster
                for cluster in new_clusters or clusters
                if cluster.contains_handle(self.expected_handle)
            ]
            if not target_rosters:
                target_rosters = snapshot.clusters_for_handle(self.expected_handle)
            self._active_rosters = target_rosters
        return snapshot

    def _apply_roster_to_candidates(self) -> None:
        if not self._active_rosters:
            return
        for cand in self._candidates.values():
            for cluster in self._active_rosters:
                if not cluster.contains_handle(self.expected_handle):
                    continue
                if cluster.contains_address(cand.address):
                    cand.in_channel_roster = True
                    cand.channel_roster_members = cluster.member_count
                    cand.notes.append(
                        f"channel roster {cluster.member_count}p @ 0x{cluster.span_start:X}"
                    )
                    break

    def initial_scan(self) -> TraceMonitorTick:
        """CE first scan — populate candidate watch list."""
        self._modules = build_module_map(self._pid)
        scan_fn = make_scan_bytes_fn(self.strategies)
        name_hits = scan_process_for_decoded_strings(
            self._process,
            self.expected_name,
            scan_fn,
            strategies=self.strategies,
            time_budget_sec=12.0,
            max_hits=self.max_candidates,
        )
        handle_hits = scan_process_for_decoded_handles(
            self._process,
            self.expected_handle,
            scan_fn,
            strategies=self.strategies,
            time_budget_sec=12.0,
            max_hits=self.max_candidates,
        )
        self._bootstrap_host_anchor()
        if self._host_anchor is not None:
            _seed_handle_hits_from_host_anchor(
                self._process,
                modules=self._modules,
                expected_handle=self.expected_handle,
                strategies=self.strategies,
                handle_hits=handle_hits,
            )
        standalone_names, standalone_handles = _build_standalone_hits(
            self._process,
            pid=self._pid,
            name_hits=name_hits,
            handle_hits=handle_hits,
            expected_name=self.expected_name,
            strategies=self.strategies,
        )
        _boost_standalone_with_host_anchor(
            self._process,
            modules=self._modules,
            expected_handle=self.expected_handle,
            strategies=self.strategies,
            standalone_handles=standalone_handles,
            anchor=self._host_anchor,
        )

        for hit in standalone_names[: self.max_candidates]:
            self._register_hit("name", hit)
        for hit in standalone_handles[: self.max_candidates]:
            self._register_hit("handle", hit)

        self._last_scan_names = {item.address for item in name_hits}
        self._last_scan_handles = {item.address for item in handle_hits}
        roster_snap = self._scan_room_channel_rosters(RoomPhase.OUT)
        self._apply_roster_to_candidates()
        self._initialized = True

        event = TraceMonitorTick(
            phase=self.phase,
            cycle=self.cycle,
            message=(
                f"初次扫描: 昵称 {len(self._last_scan_names)} 处, "
                f"句柄 {len(self._last_scan_handles)} 处, "
                f"监控 {len(self._candidates)} 个候选, "
                f"频道 roster {len(roster_snap.clusters)} 组"
                + (
                    f", 主机锚点 {self._host_anchor.handle}"
                    if self._host_anchor is not None
                    else ""
                )
            ),
            scan_name_count=len(self._last_scan_names),
            scan_handle_count=len(self._last_scan_handles),
        )
        self.events.append(event)
        return event

    def _register_hit(self, kind: str, hit: StandaloneHit) -> None:
        key = _candidate_key(kind, hit.address)
        if key in self._candidates:
            return
        self._candidates[key] = TraceCandidate(
            kind=kind,
            address=hit.address,
            region_type=hit.region_type,
            module_label=hit.location.module_label,
            lobby_score=hit.lobby_score,
            strategy=hit.strategy,
        )
        data = _read_field_bytes(
            self._process,
            hit.address,
            kind,
            self.expected_name,
            self.expected_handle,
        )
        self._candidates[key].last_bytes_hash = _bytes_hash(data)

    def mark_player_in_room(self) -> TraceMonitorTick:
        return self._transition(RoomPhase.IN)

    def mark_player_out_room(self) -> TraceMonitorTick:
        return self._transition(RoomPhase.OUT)

    def _transition(self, new_phase: RoomPhase) -> TraceMonitorTick:
        if not self._initialized:
            self.initial_scan()

        prev_phase = self.phase
        if prev_phase == RoomPhase.OUT and new_phase == RoomPhase.IN:
            self.cycle += 1
        if prev_phase == RoomPhase.IN and new_phase == RoomPhase.OUT:
            pass

        name_addrs, handle_addrs = self._scan_addresses()
        self._apply_phase_scan(name_addrs, handle_addrs, phase=new_phase)
        roster_snap = self._scan_room_channel_rosters(new_phase)
        self._apply_roster_to_candidates()

        if prev_phase == RoomPhase.OUT and new_phase == RoomPhase.IN:
            for addr in name_addrs:
                self._note_enter("name", addr)
            for addr in handle_addrs:
                self._note_enter("handle", addr)
        elif prev_phase == RoomPhase.IN and new_phase == RoomPhase.OUT:
            for addr in self._last_scan_names:
                if addr not in name_addrs:
                    self._note_leave_absent("name", addr)
            for addr in self._last_scan_handles:
                if addr not in handle_addrs:
                    self._note_leave_absent("handle", addr)

        self._last_scan_names = name_addrs
        self._last_scan_handles = handle_addrs
        self.phase = new_phase

        newly_confirmed: list[TraceCandidate] = []
        for cand in self._candidates.values():
            was = cand.confirmed
            is_confirmed_candidate(cand)
            if cand.confirmed and not was:
                newly_confirmed.append(cand)

        label = "进房" if new_phase == RoomPhase.IN else "离房"
        target_rosters = [
            cluster
            for cluster in roster_snap.clusters
            if cluster.contains_handle(self.expected_handle)
        ]
        event = TraceMonitorTick(
            phase=new_phase,
            cycle=self.cycle,
            message=(
                f"标记{label} (循环 {self.cycle}): 扫描昵称 {len(name_addrs)} / "
                f"句柄 {len(handle_addrs)}, 频道 roster {len(roster_snap.clusters)} 组 "
                f"(含目标 {len(target_rosters)}), 新确认 {len(newly_confirmed)}"
            ),
            scan_name_count=len(name_addrs),
            scan_handle_count=len(handle_addrs),
            newly_confirmed=newly_confirmed,
        )
        self.events.append(event)
        return event

    def _apply_phase_scan(self, name_addrs: set[int], handle_addrs: set[int], *, phase: RoomPhase) -> None:
        for kind, addrs in (("name", name_addrs), ("handle", handle_addrs)):
            for addr in addrs:
                key = _candidate_key(kind, addr)
                if key not in self._candidates:
                    location = locate_address(
                        addr,
                        modules=self._modules,
                        process_handle=self._process,
                    )
                    if kind == "name":
                        probe = score_name_probe(
                            NameProbeResult(
                                name=self.expected_name,
                                name_address=addr,
                                name_encoding="utf16_le_z",
                                location=location,
                                handles=[],
                            )
                        )
                        score = probe.lobby_score
                    else:
                        score, _ = _score_handle_location(location)
                    self._candidates[key] = TraceCandidate(
                        kind=kind,
                        address=addr,
                        region_type=location.region_type,
                        module_label=location.module_label,
                        lobby_score=score,
                    )
                    data = _read_field_bytes(
                        self._process,
                        addr,
                        kind,
                        self.expected_name,
                        self.expected_handle,
                    )
                    self._candidates[key].last_bytes_hash = _bytes_hash(data)

                cand = self._candidates[key]
                if phase == RoomPhase.IN:
                    cand.seen_in_room += 1
                else:
                    cand.seen_out_room += 1

    def _note_enter(self, kind: str, address: int) -> None:
        key = _candidate_key(kind, address)
        cand = self._candidates.get(key)
        if cand is None:
            return
        cand.present_after_enter += 1
        cand.notes.append(f"enter+0x{address:X}")

    def _note_leave_absent(self, kind: str, address: int) -> None:
        key = _candidate_key(kind, address)
        cand = self._candidates.get(key)
        if cand is None:
            return
        cand.absent_after_leave += 1
        cand.notes.append(f"leave-0x{address:X}")

    def poll_writes(self) -> TraceMonitorTick:
        """Poll watched addresses for byte changes (CE memory view refresh)."""
        write_events: list[tuple[str, int]] = []
        for cand in self._candidates.values():
            data = _read_field_bytes(
                self._process,
                cand.address,
                cand.kind,
                self.expected_name,
                self.expected_handle,
            )
            digest = _bytes_hash(data)
            if cand.last_bytes_hash and digest != cand.last_bytes_hash:
                still_ok = _still_matches(
                    self._process,
                    cand.address,
                    cand.kind,
                    self.expected_name,
                    self.expected_handle,
                )
                if still_ok or cand.kind == "name":
                    cand.write_events += 1
                    cand.last_change_at = time.time()
                    write_events.append((cand.kind, cand.address))
                    cand.notes.append(f"write@{time.strftime('%H:%M:%S')}")
            cand.last_bytes_hash = digest

        newly_confirmed: list[TraceCandidate] = []
        for cand in self._candidates.values():
            was = cand.confirmed
            is_confirmed_candidate(cand)
            if cand.confirmed and not was:
                newly_confirmed.append(cand)

        event = TraceMonitorTick(
            phase=self.phase,
            cycle=self.cycle,
            message=f"写入轮询: {len(write_events)} 处变化",
            write_events=write_events,
            newly_confirmed=newly_confirmed,
        )
        return event

    def tick(self) -> TraceMonitorTick:
        self._tick_count += 1
        poll = self.poll_writes()

        if self._tick_count % self.rescan_every_ticks == 0:
            name_addrs, handle_addrs = self._scan_addresses()
            self._apply_phase_scan(name_addrs, handle_addrs, phase=self.phase)
            self._last_scan_names = name_addrs
            self._last_scan_handles = handle_addrs
            poll.message += (
                f"; 重扫 昵称 {len(name_addrs)} / 句柄 {len(handle_addrs)}"
            )
            poll.scan_name_count = len(name_addrs)
            poll.scan_handle_count = len(handle_addrs)

        self.events.append(poll)
        return poll

    def build_report(self) -> TraceMonitorReport:
        for cand in self._candidates.values():
            is_confirmed_candidate(cand)

        confirmed_names = [c.address for c in self.candidates if c.confirmed and c.kind == "name"]
        confirmed_handles = [
            c.address for c in self.candidates if c.confirmed and c.kind == "handle"
        ]
        region_types = {
            c.address: c.region_type
            for c in self._candidates.values()
        }
        for c in self._candidates.values():
            region_types[c.address] = c.region_type

        struct_bases = infer_struct_bases(
            confirmed_names,
            confirmed_handles,
            region_types=region_types,
        )

        pointer_chains: list[PointerChain] = []
        if not self._modules:
            self._modules = build_module_map(self._pid)
        for addr in confirmed_names[:2] + confirmed_handles[:2]:
            pointer_chains.extend(
                trace_pointer_roots_iterative(
                    self._process,
                    addr,
                    self._modules,
                    max_depth=3,
                    max_chains=4,
                )
            )

        return TraceMonitorReport(
            expected_name=self.expected_name,
            expected_handle=self.expected_handle,
            candidates=sorted(
                self._candidates.values(),
                key=lambda c: c.confirm_score,
                reverse=True,
            ),
            struct_bases=struct_bases,
            pointer_chains=pointer_chains[:12],
            cycles_completed=self.cycle,
            channel_rosters=list(self._active_rosters or []),
        )

    @property
    def candidates(self) -> list[TraceCandidate]:
        return sorted(
            self._candidates.values(),
            key=lambda c: c.confirm_score,
            reverse=True,
        )
