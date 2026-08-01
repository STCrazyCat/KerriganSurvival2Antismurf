"""Discover in-room lobby roster base via CE-style in/out diff on profile bytes.

Workflow (automated helper for Mode 5):
1. Baseline scan (optional, lobby without created room).
2. Create KS2 room as host → scan for host ``profile_id`` (3-byte LE tail).
3. Exit / destroy room → rescan and diff.
4. Addresses that appear in-room and vanish on exit → roster field candidates.
5. Derive ``record_base = profile_addr - 0x20`` when lobby struct header validates.
"""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass, field
from enum import Enum

from antismurf.lobby.memory_lobby_roster import (
    LOBBY_MEMBER_RECORD_SIZE,
    OFF_MEMBER_PROFILE_ID,
    parse_lobby_member_record,
    read_roster_members_at_base,
    verify_lobby_member_record_at,
)
from antismurf.lobby.memory_host_anchor import DEFAULT_SC2_MODULE_NAMES
from antismurf.lobby.memory_probe import ModuleInfo, build_module_map, locate_address
from antismurf.lobby.memory_reader import (
    _iter_readable_regions_typed,
    _read_memory,
)
from antismurf.models.player import parse_handle_parts


class DiscoveryPhase(str, Enum):
    IDLE = "idle"
    BASELINE = "baseline"
    IN_ROOM = "in_room"
    AFTER_EXIT = "after_exit"


@dataclass(frozen=True)
class ProfileScanHit:
    address: int
    profile_id: int
    width: int
    region_type: str


@dataclass
class RosterDiscoverySnapshot:
    phase: DiscoveryPhase
    timestamp: float
    host_handle: str
    profile_addresses: set[int] = field(default_factory=set)
    hits: list[ProfileScanHit] = field(default_factory=list)

    @property
    def hit_count(self) -> int:
        return len(self.profile_addresses)


@dataclass
class RosterBaseCandidate:
    record_base: int
    profile_address: int
    score: float
    region_type: str
    member_count: int = 0
    host_handle: str = ""
    host_name: str | None = None
    appeared_in_room: bool = False
    vanished_on_exit: bool = False
    struct_valid: bool = False
    notes: list[str] = field(default_factory=list)

    def summary_line(self) -> str:
        flag = "★" if self.struct_valid and self.vanished_on_exit else "·"
        name = f' "{self.host_name}"' if self.host_name else ""
        return (
            f"{flag} roster 基址 0x{self.record_base:X} "
            f"profile@0x{self.profile_address:X} ({self.region_type}) "
            f"成员≈{self.member_count} 分={self.score:.0f}{name} | "
            f"{'进房出现' if self.appeared_in_room else ''}"
            f"{' 出房消失' if self.vanished_on_exit else ''} | "
            f"{'; '.join(self.notes[:2])}"
        )


@dataclass
class RosterBaseConfirmation:
    """Automated verdict after Mode 5 analyze."""

    confirmed: bool
    confidence: str  # high | medium | low
    record_base: int | None = None
    profile_address: int | None = None
    reasons: list[str] = field(default_factory=list)

    def summary_line(self) -> str:
        base = f"0x{self.record_base:X}" if self.record_base is not None else "?"
        verdict = "已确认" if self.confirmed else "未确认"
        detail = "; ".join(self.reasons[:4]) if self.reasons else "无"
        return f"[{self.confidence}] {verdict} roster 基址 {base} | {detail}"


@dataclass
class RosterDiscoveryReport:
    host_handle: str
    profile_byte_width: int
    snapshots: list[RosterDiscoverySnapshot] = field(default_factory=list)
    candidates: list[RosterBaseCandidate] = field(default_factory=list)
    best: RosterBaseCandidate | None = None

    def summary_lines(self) -> list[str]:
        lines = [
            f"主机句柄: {self.host_handle}",
            f"profile 扫描宽度: {self.profile_byte_width} 字节",
            f"阶段快照: {len(self.snapshots)}",
        ]
        for snap in self.snapshots:
            lines.append(f"  [{snap.phase.value}] {snap.hit_count} 处 profile 命中")
        lines.append(f"roster 基址候选: {len(self.candidates)}")
        if self.best is not None:
            lines.append(f"推荐: {self.best.summary_line()}")
        return lines


def profile_id_needles(handle: str, *, width: int = 3) -> tuple[bytes, int] | None:
    parts = parse_handle_parts(handle)
    if parts is None:
        return None
    packed = struct.pack("<I", parts.player_id)
    if width == 3:
        return packed[:3], parts.player_id
    return packed, parts.player_id


def scan_profile_field_addresses(
    process_handle,
    host_handle: str,
    *,
    profile_byte_width: int = 3,
    time_budget_sec: float = 12.0,
    prefer_private: bool = True,
    max_hits: int = 4000,
) -> list[ProfileScanHit]:
    """Scan readable memory for host profile_id bytes (default: 3-byte LE tail)."""
    parsed = profile_id_needles(host_handle, width=profile_byte_width)
    if parsed is None:
        return []
    needle, profile_id = parsed

    hits: list[ProfileScanHit] = []
    seen: set[int] = set()
    started = time.perf_counter()
    regions: list[tuple[int, int, str]] = list(
        _iter_readable_regions_typed(process_handle)
    )
    if prefer_private:
        regions.sort(key=lambda item: (0 if item[2] == "private" else 1, -item[0]))

    for region_base, region_size, region_type in regions:
        if time.perf_counter() - started > time_budget_sec:
            break
        if prefer_private and region_type == "image":
            continue
        if region_size > 32 * 1024 * 1024:
            region_size = 32 * 1024 * 1024
        offset = 0
        while offset < region_size:
            if time.perf_counter() - started > time_budget_sec:
                break
            if len(hits) >= max_hits:
                return hits
            read_size = min(65536, region_size - offset)
            data = _read_memory(process_handle, region_base + offset, read_size)
            if not data:
                offset += read_size
                continue
            pos = 0
            while True:
                found = data.find(needle, pos)
                if found < 0:
                    break
                address = region_base + offset + found
                pos = found + 1
                if address in seen:
                    continue
                if not _verify_profile_width_at(
                    process_handle,
                    address,
                    host_handle,
                    width=profile_byte_width,
                ):
                    continue
                seen.add(address)
                hits.append(
                    ProfileScanHit(
                        address=address,
                        profile_id=profile_id,
                        width=profile_byte_width,
                        region_type=region_type,
                    )
                )
                if len(hits) >= max_hits:
                    return hits
            offset += read_size

    if not prefer_private or len(hits) < 4:
        extra_budget = max(2.0, time_budget_sec * 0.35)
        for region_base, region_size, region_type in regions:
            if time.perf_counter() - started > time_budget_sec + extra_budget:
                break
            if region_type == "image":
                continue
            offset = 0
            while offset < region_size:
                if len(hits) >= max_hits:
                    return hits
                read_size = min(65536, region_size - offset)
                data = _read_memory(process_handle, region_base + offset, read_size)
                if not data:
                    offset += read_size
                    continue
                pos = 0
                while True:
                    found = data.find(needle, pos)
                    if found < 0:
                        break
                    address = region_base + offset + found
                    pos = found + 1
                    if address in seen:
                        continue
                    if not _verify_profile_width_at(
                        process_handle,
                        address,
                        host_handle,
                        width=profile_byte_width,
                    ):
                        continue
                    seen.add(address)
                    hits.append(
                        ProfileScanHit(
                            address=address,
                            profile_id=profile_id,
                            width=profile_byte_width,
                            region_type=region_type,
                        )
                    )
                offset += read_size
    return hits


def _find_sc2_module(modules: list[ModuleInfo]) -> ModuleInfo | None:
    lowered = {name.lower() for name in DEFAULT_SC2_MODULE_NAMES}
    for module in modules:
        if module.name.lower() in lowered:
            return module
    for module in modules:
        if module.name.lower().startswith("sc2"):
            return module
    return None


def describe_profile_address(
    process_handle,
    profile_address: int,
    *,
    pid: int | None = None,
    host_handle: str | None = None,
    ce_module_base: int | None = None,
) -> list[str]:
    """Explain a CE-found profile field address and inferred roster record base."""
    record_base = profile_address - OFF_MEMBER_PROFILE_ID
    modules = build_module_map(pid) if pid else []
    location = locate_address(
        profile_address,
        modules=modules,
        process_handle=process_handle,
    )
    lines = [
        f"CE profile @ 0x{profile_address:X}",
        f"推算 roster record_base @ 0x{record_base:X} (profile - 0x{OFF_MEMBER_PROFILE_ID:X})",
        f"内存区域: {location.region_type}  region_base=0x{location.region_base:X}",
    ]

    sc2 = _find_sc2_module(modules)
    if sc2 is not None:
        lines.append(f"当前进程 SC2 模块基址: 0x{sc2.base:X} ({sc2.name})")
        delta = profile_address - sc2.base
        if location.region_type == "image":
            lines.append(f"模块内 RVA: 0x{delta:X}")
        else:
            lines.append(
                f"距 SC2 基址偏移 {delta:+d} — 动态堆/映射区，"
                "不能作为静态 module+offset 基址"
            )
    if ce_module_base is not None:
        lines.append(f"CE 会话模块基址: 0x{ce_module_base:X}")
        if sc2 is not None:
            base_shift = sc2.base - ce_module_base
            lines.append(f"模块基址 ASLR 漂移: {base_shift:+d} (当前 - CE)")
        ce_delta = profile_address - ce_module_base
        lines.append(f"相对 CE 模块基址偏移: {ce_delta:+d}")

    if host_handle:
        struct_valid = verify_lobby_member_record_at(
            process_handle,
            record_base,
            host_handle,
        )
        lines.append(
            "lobby struct 头验证: "
            + ("通过" if struct_valid else "未通过（可能已退房或句柄不匹配）")
        )
        if struct_valid:
            member_count = count_members_from_record_base(process_handle, record_base)
            lines.append(f"stride 0x{LOBBY_MEMBER_RECORD_SIZE:X} 连续成员 ≈{member_count}")
    else:
        lines.append("提示: 填写玩家句柄或点「读取主机句柄」可验证 struct 头")

    return lines


def _verify_profile_width_at(
    process_handle,
    profile_address: int,
    expected_handle: str,
    *,
    width: int,
) -> bool:
    parts = parse_handle_parts(expected_handle)
    if parts is None:
        return False
    blob = _read_memory(process_handle, profile_address, 4)
    if not blob or len(blob) < width:
        return False
    if width == 3:
        packed = struct.pack("<I", parts.player_id)
        return blob[:3] == packed[:3]
    return struct.unpack_from("<I", blob, 0)[0] == parts.player_id


def count_members_from_record_base(
    process_handle,
    record_base: int,
    *,
    max_members: int = 12,
) -> int:
    return len(
        read_roster_members_at_base(
            process_handle,
            record_base,
            max_members=max_members,
        )
    )


def _score_roster_candidate(
    process_handle,
    profile_address: int,
    host_handle: str,
    *,
    appeared_in_room: bool,
    vanished_on_exit: bool,
    pid: int | None = None,
) -> RosterBaseCandidate:
    record_base = profile_address - OFF_MEMBER_PROFILE_ID
    modules = build_module_map(pid) if pid else []
    location = locate_address(
        profile_address,
        modules=modules,
        process_handle=process_handle,
    )
    struct_valid = verify_lobby_member_record_at(
        process_handle,
        record_base,
        host_handle,
    )
    member_count = count_members_from_record_base(process_handle, record_base)
    host_name: str | None = None
    if struct_valid:
        blob = _read_memory(process_handle, record_base, LOBBY_MEMBER_RECORD_SIZE) or b""
        record = parse_lobby_member_record(blob, record_base=record_base, rel_base=0)
        if record is not None:
            host_name = record.display_name

    score = 0.0
    notes: list[str] = []
    if appeared_in_room:
        score += 30.0
        notes.append("进房出现 (+30)")
    if vanished_on_exit:
        score += 45.0
        notes.append("出房消失 (+45)")
    if appeared_in_room and vanished_on_exit:
        score += 20.0
        notes.append("完整进退房 (+20)")
    if struct_valid:
        score += 40.0
        notes.append("lobby struct 头 (+40)")
    if location.region_type == "private":
        score += 25.0
        notes.append("private heap (+25)")
    elif location.region_type == "mapped":
        score += 10.0
    if member_count >= 2:
        score += 20.0
        notes.append(f"{member_count} 成员 stride (+20)")
    elif member_count == 1:
        score += 8.0
        notes.append("1 成员 (+8)")

    return RosterBaseCandidate(
        record_base=record_base,
        profile_address=profile_address,
        score=score,
        region_type=location.region_type,
        member_count=member_count,
        host_handle=host_handle,
        host_name=host_name,
        appeared_in_room=appeared_in_room,
        vanished_on_exit=vanished_on_exit,
        struct_valid=struct_valid,
        notes=notes,
    )


def analyze_roster_discovery(
    process_handle,
    *,
    host_handle: str,
    snapshots: list[RosterDiscoverySnapshot],
    pid: int | None = None,
) -> RosterDiscoveryReport:
    by_phase = {snap.phase: snap for snap in snapshots}
    baseline = by_phase.get(DiscoveryPhase.BASELINE)
    in_room = by_phase.get(DiscoveryPhase.IN_ROOM)
    after_exit = by_phase.get(DiscoveryPhase.AFTER_EXIT)

    width = 3
    if snapshots:
        width = 3  # default; could read from session

    if in_room is None:
        return RosterDiscoveryReport(
            host_handle=host_handle,
            profile_byte_width=width,
            snapshots=list(snapshots),
        )

    baseline_addrs = baseline.profile_addresses if baseline else set()
    in_addrs = in_room.profile_addresses
    after_addrs = after_exit.profile_addresses if after_exit else set()

    appeared = in_addrs - baseline_addrs
    vanished = in_addrs - after_addrs if after_exit else set()
    key_profiles = appeared & vanished if vanished else appeared

    candidates: list[RosterBaseCandidate] = []
    for profile_addr in key_profiles:
        candidates.append(
            _score_roster_candidate(
                process_handle,
                profile_addr,
                host_handle,
                appeared_in_room=profile_addr in appeared,
                vanished_on_exit=profile_addr in vanished if after_exit else False,
                pid=pid,
            )
        )

    if after_exit:
        for profile_addr in in_addrs:
            if profile_addr in after_addrs:
                continue
            if not _profile_still_matches(
                process_handle,
                profile_addr,
                host_handle,
                width=width,
            ):
                cand = _score_roster_candidate(
                    process_handle,
                    profile_addr,
                    host_handle,
                    appeared_in_room=True,
                    vanished_on_exit=True,
                    pid=pid,
                )
                if cand.profile_address not in {c.profile_address for c in candidates}:
                    candidates.append(cand)

    by_profile: dict[int, RosterBaseCandidate] = {}
    for cand in candidates:
        prev = by_profile.get(cand.profile_address)
        if prev is None or cand.score > prev.score:
            by_profile[cand.profile_address] = cand
    candidates = list(by_profile.values())

    candidates.sort(
        key=lambda item: (
            item.vanished_on_exit,
            item.appeared_in_room and item.vanished_on_exit,
            item.struct_valid,
            item.score,
        ),
        reverse=True,
    )
    best = candidates[0] if candidates else None
    return RosterDiscoveryReport(
        host_handle=host_handle,
        profile_byte_width=width,
        snapshots=list(snapshots),
        candidates=candidates,
        best=best,
    )


def evaluate_roster_confirmation(
    report: RosterDiscoveryReport,
) -> RosterBaseConfirmation:
    """Decide whether Mode 5 diff workflow confirmed a roster record base."""
    phases = {snap.phase for snap in report.snapshots}
    if report.best is None:
        return RosterBaseConfirmation(
            confirmed=False,
            confidence="low",
            reasons=["无 roster 候选，请先完成进/出房扫描"],
        )

    best = report.best
    reasons: list[str] = []

    if DiscoveryPhase.IN_ROOM not in phases:
        reasons.append("缺少「已创建房间」快照")
        return RosterBaseConfirmation(
            confirmed=False,
            confidence="low",
            record_base=best.record_base,
            profile_address=best.profile_address,
            reasons=reasons,
        )

    if DiscoveryPhase.AFTER_EXIT in phases:
        if best.appeared_in_room and best.vanished_on_exit:
            reasons.append("进房出现且出房消失（CE diff 主信号）")
            if best.struct_valid:
                reasons.append("lobby struct 头验证通过")
            if best.member_count >= 1:
                reasons.append(f"stride 0x1B8 可读成员 ≈{best.member_count}")
            return RosterBaseConfirmation(
                confirmed=True,
                confidence="high",
                record_base=best.record_base,
                profile_address=best.profile_address,
                reasons=reasons,
            )
        reasons.append("出房后 profile 未完全消失，diff 不可靠")
        return RosterBaseConfirmation(
            confirmed=False,
            confidence="low",
            record_base=best.record_base,
            profile_address=best.profile_address,
            reasons=reasons,
        )

    if best.appeared_in_room and best.struct_valid:
        reasons.append("仅进房快照：struct 头与 profile 匹配")
        if best.member_count >= 1:
            reasons.append(f"可读成员 ≈{best.member_count}")
        return RosterBaseConfirmation(
            confirmed=True,
            confidence="medium",
            record_base=best.record_base,
            profile_address=best.profile_address,
            reasons=reasons,
        )

    reasons.append("建议补做「已退出房间」扫描以完成 diff 确认")
    return RosterBaseConfirmation(
        confirmed=False,
        confidence="low",
        record_base=best.record_base,
        profile_address=best.profile_address,
        reasons=reasons,
    )


def _profile_still_matches(
    process_handle,
    profile_address: int,
    host_handle: str,
    *,
    width: int,
) -> bool:
    return _verify_profile_width_at(
        process_handle,
        profile_address,
        host_handle,
        width=width,
    )


class RosterDiscoverySession:
    """Mode 5: host profile byte diff across create-room / exit-room."""

    def __init__(
        self,
        process_handle,
        *,
        pid: int,
        host_handle: str,
        profile_byte_width: int = 3,
        scan_budget_sec: float = 12.0,
        prefer_private: bool = True,
    ) -> None:
        self._process = process_handle
        self._pid = pid
        self.host_handle = host_handle.strip()
        self.profile_byte_width = profile_byte_width
        self.scan_budget_sec = scan_budget_sec
        self.prefer_private = prefer_private
        self.snapshots: list[RosterDiscoverySnapshot] = []
        self.events: list[str] = []

    def scan_phase(self, phase: DiscoveryPhase) -> RosterDiscoverySnapshot:
        hits = scan_profile_field_addresses(
            self._process,
            self.host_handle,
            profile_byte_width=self.profile_byte_width,
            time_budget_sec=self.scan_budget_sec,
            prefer_private=self.prefer_private,
        )
        snapshot = RosterDiscoverySnapshot(
            phase=phase,
            timestamp=time.time(),
            host_handle=self.host_handle,
            profile_addresses={hit.address for hit in hits},
            hits=hits,
        )
        self.snapshots = [s for s in self.snapshots if s.phase != phase]
        self.snapshots.append(snapshot)
        msg = (
            f"[{phase.value}] profile {self.profile_byte_width}B 扫描: "
            f"{snapshot.hit_count} 处 (主机 {self.host_handle})"
        )
        self.events.append(msg)
        return snapshot

    def analyze(self) -> RosterDiscoveryReport:
        report = analyze_roster_discovery(
            self._process,
            host_handle=self.host_handle,
            snapshots=self.snapshots,
            pid=self._pid,
        )
        confirmation = evaluate_roster_confirmation(report)
        if confirmation.confirmed:
            self.events.append(confirmation.summary_line())
        elif report.best is not None:
            self.events.append(
                f"候选 roster 基址 0x{report.best.record_base:X}（{confirmation.confidence}）"
            )
        else:
            self.events.append("未找到可靠 roster 基址，请重试进/出房流程")
        return report

    def read_roster_at_best(self, report: RosterDiscoveryReport) -> list[str]:
        if report.best is None:
            return []
        lines: list[str] = []
        base = report.best.record_base
        blob = _read_memory(
            self._process,
            base,
            LOBBY_MEMBER_RECORD_SIZE * max(4, report.best.member_count),
        )
        if not blob:
            return lines
        for index in range(max(4, report.best.member_count)):
            rel = index * LOBBY_MEMBER_RECORD_SIZE
            if rel + LOBBY_MEMBER_RECORD_SIZE > len(blob):
                break
            record = parse_lobby_member_record(
                blob,
                record_base=base + rel,
                rel_base=rel,
            )
            if record is None:
                break
            lines.append(f"  [{index}] {record.summary_line()}")
        return lines
