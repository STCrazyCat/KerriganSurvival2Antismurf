"""SC2 lobby memory probe — locate display-name ↔ handle associations (CE-style helper).

Use this module to study how nicknames and Battle.net handles are laid out in
``SC2_x64.exe`` process memory before tightening production lobby scanning.
"""

from __future__ import annotations

import ctypes
import struct
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from antismurf.lobby.memory_formats import (
    ProfileTriplet,
    extract_handle_hits,
    extract_profile_triplets,
    scan_sc2_byte_strings,
    scan_utf16le_null_strings,
)
from antismurf.lobby.memory_host_anchor import (
    HostHandleAnchor,
    anchor_proximity_bonus,
    read_host_handle_anchor,
    scan_module_vicinity_handles,
)
from antismurf.lobby.memory_channel_roster import (
    pick_handle_address_in_cluster,
    pick_name_in_roster_window,
    scan_channel_rosters,
)
from antismurf.lobby.memory_lobby_roster import (
    verify_lobby_name_utf8_at,
    verify_lobby_profile_id_at,
    scan_process_for_lobby_profile_handle,
)
from antismurf.lobby.memory_scan_strategies import (
    DEFAULT_SCAN_STRATEGIES,
    ComprehensiveScanStats,
    DecodedHandleHit,
    ScanStrategies,
    collect_handles_in_window,
    collect_names_in_window,
    scan_process_for_decoded_handles,
    scan_process_for_decoded_strings,
    verify_handle_bytes_at,
    verify_name_bytes_at,
)
from antismurf.lobby.memory_reader import (
    MEMORY_BASIC_INFORMATION,
    _iter_readable_regions,
    _iter_readable_regions_typed,
    _read_memory,
    iter_readable_regions_heap_first,
)
from antismurf.lobby.sc2_process import close_process, get_sc2_pid, open_process_for_read
from antismurf.models.player import is_valid_handle, parse_handle_parts

MEM_PRIVATE = 0x20000
MEM_MAPPED = 0x40000
MEM_IMAGE = 0x1000000

REGION_TYPE_LABELS = {
    MEM_PRIVATE: "private",
    MEM_MAPPED: "mapped",
    MEM_IMAGE: "image",
}


@dataclass(frozen=True)
class ModuleInfo:
    name: str
    base: int
    size: int


@dataclass(frozen=True)
class MemoryLocation:
    address: int
    region_base: int
    region_size: int
    protect: int
    region_type: str
    module_name: str | None = None
    module_offset: int | None = None

    @property
    def module_label(self) -> str:
        if self.module_name and self.module_offset is not None:
            return f"{self.module_name}+0x{self.module_offset:X}"
        return f"0x{self.address:X}"


@dataclass(frozen=True)
class HandleNearName:
    handle: str
    handle_address: int
    offset_from_name: int
    encoding: str = "ascii_z"


@dataclass(frozen=True)
class TripletNearName:
    triplet: ProfileTriplet
    triplet_address: int
    handle: str
    offset_from_name: int


@dataclass
class NameProbeResult:
    name: str
    name_address: int
    name_encoding: str
    location: MemoryLocation
    handles: list[HandleNearName] = field(default_factory=list)
    triplets: list[TripletNearName] = field(default_factory=list)
    lobby_score: float = 0.0
    score_notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "name_address": hex(self.name_address),
            "name_encoding": self.name_encoding,
            "location": {
                "address": hex(self.location.address),
                "region_base": hex(self.location.region_base),
                "region_size": self.location.region_size,
                "region_type": self.location.region_type,
                "module": self.location.module_label,
            },
            "lobby_score": round(self.lobby_score, 2),
            "score_notes": self.score_notes,
            "handles": [
                {
                    "handle": item.handle,
                    "address": hex(item.handle_address),
                    "offset_from_name": item.offset_from_name,
                }
                for item in self.handles
            ],
            "triplets": [
                {
                    "handle": item.handle,
                    "address": hex(item.triplet_address),
                    "offset_from_name": item.offset_from_name,
                }
                for item in self.triplets
            ],
        }


def iter_process_modules(pid: int) -> Iterator[ModuleInfo]:
    """Enumerate loaded modules for ``pid`` (64-bit process)."""
    TH32CS_SNAPMODULE = 0x00000008
    TH32CS_SNAPMODULE32 = 0x00000010
    kernel32 = ctypes.windll.kernel32

    class MODULEENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", ctypes.c_ulong),
            ("th32ModuleID", ctypes.c_ulong),
            ("th32ProcessID", ctypes.c_ulong),
            ("GlblcntUsage", ctypes.c_ulong),
            ("ProccntUsage", ctypes.c_ulong),
            ("modBaseAddr", ctypes.c_void_p),
            ("modBaseSize", ctypes.c_ulong),
            ("hModule", ctypes.c_void_p),
            ("szModule", ctypes.c_wchar * 256),
            ("szExePath", ctypes.c_wchar * 260),
        ]

    snapshot = kernel32.CreateToolhelp32Snapshot(
        TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32,
        int(pid),
    )
    if snapshot in (-1, 0xFFFFFFFFFFFFFFFF):
        return

    entry = MODULEENTRY32W()
    entry.dwSize = ctypes.sizeof(MODULEENTRY32W)
    try:
        if not kernel32.Module32FirstW(snapshot, ctypes.byref(entry)):
            return
        while True:
            base = int(ctypes.cast(entry.modBaseAddr, ctypes.c_void_p).value or 0)
            size = int(entry.modBaseSize)
            if base and size:
                yield ModuleInfo(name=entry.szModule, base=base, size=size)
            if not kernel32.Module32NextW(snapshot, ctypes.byref(entry)):
                break
    finally:
        kernel32.CloseHandle(snapshot)


def build_module_map(pid: int) -> list[ModuleInfo]:
    return sorted(iter_process_modules(pid), key=lambda item: item.base)


def locate_address(
    address: int,
    *,
    modules: list[ModuleInfo],
    process_handle=None,
) -> MemoryLocation:
    region_base = 0
    region_size = 0
    protect = 0
    region_type = "unknown"
    if process_handle is not None:
        mbi = MEMORY_BASIC_INFORMATION()
        result = ctypes.windll.kernel32.VirtualQueryEx(
            process_handle,
            ctypes.c_void_p(address),
            ctypes.byref(mbi),
            ctypes.sizeof(mbi),
        )
        if result:
            region_base = int(ctypes.cast(mbi.BaseAddress, ctypes.c_void_p).value or 0)
            region_size = int(mbi.RegionSize)
            protect = int(mbi.Protect)
            region_type = REGION_TYPE_LABELS.get(int(mbi.Type), f"type_{int(mbi.Type)}")

    module_name: str | None = None
    module_offset: int | None = None
    for module in modules:
        if module.base <= address < module.base + module.size:
            module_name = module.name
            module_offset = address - module.base
            break

    return MemoryLocation(
        address=address,
        region_base=region_base,
        region_size=region_size,
        protect=protect,
        region_type=region_type,
        module_name=module_name,
        module_offset=module_offset,
    )


def scan_process_for_bytes(
    process_handle,
    needle: bytes,
    *,
    chunk_size: int = 65536,
    time_budget_sec: float = 30.0,
    max_hits: int = 200,
    prefer_heap_first: bool = False,
    max_image_hits: int = 8,
) -> list[int]:
    hits: list[int] = []
    image_hits = 0
    started = time.perf_counter()
    region_iter: Iterator[tuple[int, int]] = (
        iter_readable_regions_heap_first(process_handle)
        if prefer_heap_first
        else _iter_readable_regions(process_handle, heap_only=False)
    )
    region_types: dict[int, str] = {}
    if prefer_heap_first and max_image_hits >= 0:
        for base, _size, region_type in _iter_readable_regions_typed(process_handle):
            region_types[base] = region_type

    for base, size in region_iter:
        if time.perf_counter() - started > time_budget_sec:
            break
        region_type = region_types.get(base, "unknown")
        offset = 0
        while offset < size:
            if time.perf_counter() - started > time_budget_sec:
                break
            if len(hits) >= max_hits:
                return hits
            read_size = min(chunk_size, size - offset)
            data = _read_memory(process_handle, base + offset, read_size)
            if not data:
                offset += read_size
                continue
            pos = 0
            while True:
                found = data.find(needle, pos)
                if found < 0:
                    break
                address = base + offset + found
                if region_type == "image":
                    if image_hits >= max_image_hits:
                        pos = found + 1
                        continue
                    image_hits += 1
                hits.append(address)
                if len(hits) >= max_hits:
                    return hits
                pos = found + 1
            offset += read_size
    return hits


def make_scan_bytes_fn(strategies: ScanStrategies):
    """Build a byte scanner honoring heap-first and image hit caps."""

    def _scan(process_handle, needle: bytes, *, time_budget_sec: float, max_hits: int) -> list[int]:
        return scan_process_for_bytes(
            process_handle,
            needle,
            time_budget_sec=time_budget_sec,
            max_hits=max_hits,
            prefer_heap_first=strategies.prefer_heap_first,
            max_image_hits=strategies.max_image_hits,
        )

    return _scan


def scan_process_for_name(
    process_handle,
    display_name: str,
    *,
    chunk_size: int = 65536,
    time_budget_sec: float = 30.0,
    max_hits: int = 100,
) -> list[tuple[int, str]]:
    """Return ``(address, encoding)`` for UTF-16 LE and UTF-8 occurrences."""
    hits: list[tuple[int, str]] = []
    seen: set[int] = set()
    for encoding, needle in (
        ("utf16_le_z", display_name.encode("utf-16-le")),
        ("utf8_z", display_name.encode("utf-8")),
    ):
        for address in scan_process_for_bytes(
            process_handle,
            needle,
            chunk_size=chunk_size,
            time_budget_sec=time_budget_sec,
            max_hits=max_hits,
        ):
            if address in seen:
                continue
            seen.add(address)
            hits.append((address, encoding))
    return hits


def _collect_nearby_handles(
    data: bytes,
    *,
    window_base: int,
    name_address: int,
) -> list[HandleNearName]:
    found: list[HandleNearName] = []
    seen: set[tuple[int, str]] = set()
    for rel_offset, handle, _encoding in extract_handle_hits(data):
        handle_address = window_base + rel_offset
        key = (handle_address, handle)
        if key in seen:
            continue
        seen.add(key)
        found.append(
            HandleNearName(
                handle=handle,
                handle_address=handle_address,
                offset_from_name=handle_address - name_address,
                encoding="ascii_z",
            )
        )
    found.sort(key=lambda item: abs(item.offset_from_name))
    return found


def _collect_nearby_triplets(
    data: bytes,
    *,
    window_base: int,
    name_address: int,
) -> list[TripletNearName]:
    found: list[TripletNearName] = []
    seen: set[int] = set()
    for triplet in extract_profile_triplets(data, base_offset=0):
        address = window_base + triplet.offset
        if address in seen:
            continue
        seen.add(address)
        found.append(
            TripletNearName(
                triplet=triplet,
                triplet_address=address,
                handle=f"{triplet.region_id}-S2-{triplet.realm_id}-{triplet.profile_id}",
                offset_from_name=address - name_address,
            )
        )
    found.sort(key=lambda item: abs(item.offset_from_name))
    return found


def score_name_probe(result: NameProbeResult) -> NameProbeResult:
    """Heuristic: live lobby rows tend to sit in private heap, not static .exe data."""
    score = 0.0
    notes: list[str] = []

    region_type = result.location.region_type
    if region_type == "private":
        score += 40.0
        notes.append("private heap (+40)")
    elif region_type == "mapped":
        score += 20.0
        notes.append("mapped memory (+20)")
    elif region_type == "image":
        score -= 30.0
        notes.append("module image — likely static/UI template (-30)")

    if result.location.module_name and result.location.module_name.lower().startswith("sc2"):
        if region_type == "image":
            score -= 20.0
            notes.append("inside SC2.exe image (-20)")

    protect = result.location.protect
    if protect in {0x04, 0x40, 0x80}:  # RW variants
        score += 15.0
        notes.append("writable region (+15)")

    if result.handles:
        closest = result.handles[0]
        distance = abs(closest.offset_from_name)
        if distance <= 64:
            score += 35.0
            notes.append(f"handle within 64B ({distance:+d}) (+35)")
        elif distance <= 256:
            score += 25.0
            notes.append(f"handle within 256B ({distance:+d}) (+25)")
        elif distance <= 768:
            score += 10.0
            notes.append(f"handle within 768B ({distance:+d}) (+10)")
        else:
            notes.append(f"nearest handle far ({distance:+d})")

        if is_valid_handle(closest.handle):
            parts = parse_handle_parts(closest.handle)
            if parts is not None:
                score += 5.0
                notes.append("valid handle format (+5)")
    else:
        score -= 15.0
        notes.append("no ASCII handle in window (-15)")

    if result.triplets:
        closest_t = result.triplets[0]
        if abs(closest_t.offset_from_name) <= 128:
            score += 15.0
            notes.append(
                f"profile triplet within 128B ({closest_t.offset_from_name:+d}) (+15)"
            )
        if result.handles:
            if closest_t.handle == result.handles[0].handle:
                score += 20.0
                notes.append("triplet matches nearest handle (+20)")

    result.lobby_score = score
    result.score_notes = notes
    return result


def probe_name_address(
    process_handle,
    name_address: int,
    display_name: str,
    *,
    modules: list[ModuleInfo],
    radius: int = 768,
    name_encoding: str = "utf16_le_z",
) -> NameProbeResult:
    window_base = max(0, name_address - radius)
    read_size = radius * 2
    data = _read_memory(process_handle, window_base, read_size) or b""
    location = locate_address(
        name_address,
        modules=modules,
        process_handle=process_handle,
    )
    result = NameProbeResult(
        name=display_name,
        name_address=name_address,
        name_encoding=name_encoding,
        location=location,
        handles=_collect_nearby_handles(
            data,
            window_base=window_base,
            name_address=name_address,
        ),
        triplets=_collect_nearby_triplets(
            data,
            window_base=window_base,
            name_address=name_address,
        ),
    )
    return score_name_probe(result)


def probe_display_name(
    process_handle,
    display_name: str,
    *,
    pid: int,
    radius: int = 768,
    time_budget_sec: float = 30.0,
    max_hits: int = 50,
) -> list[NameProbeResult]:
    modules = build_module_map(pid)
    raw_hits = scan_process_for_name(
        process_handle,
        display_name,
        time_budget_sec=time_budget_sec,
        max_hits=max_hits,
    )
    results: list[NameProbeResult] = []
    for address, encoding in raw_hits:
        results.append(
            probe_name_address(
                process_handle,
                address,
                display_name,
                modules=modules,
                radius=radius,
                name_encoding=encoding,
            )
        )
    results.sort(key=lambda item: item.lobby_score, reverse=True)
    return results


def probe_handle_address(
    process_handle,
    handle_address: int,
    *,
    modules: list[ModuleInfo],
    radius: int = 768,
) -> dict[str, Any]:
    window_base = max(0, handle_address - radius)
    data = _read_memory(process_handle, window_base, radius * 2) or b""
    location = locate_address(
        handle_address,
        modules=modules,
        process_handle=process_handle,
    )
    names: list[dict[str, Any]] = []
    rel = handle_address - window_base
    handle_text = ""
    if 0 <= rel < len(data):
        end = data.find(b"\x00", rel)
        if end > rel:
            handle_text = data[rel:end].decode("ascii", errors="ignore")

    for decoded in scan_utf16le_null_strings(data):
        names.append(
            {
                "text": decoded.text,
                "address": hex(window_base + decoded.offset),
                "offset_from_handle": (window_base + decoded.offset) - handle_address,
                "encoding": "utf16_le_z",
            }
        )
    for decoded in scan_sc2_byte_strings(data):
        names.append(
            {
                "text": decoded.text,
                "address": hex(window_base + decoded.offset),
                "offset_from_handle": (window_base + decoded.offset) - handle_address,
                "encoding": decoded.encoding.value,
            }
        )
    names.sort(key=lambda item: abs(int(item["offset_from_handle"])))

    return {
        "handle": handle_text,
        "handle_address": hex(handle_address),
        "location": {
            "region_type": location.region_type,
            "module": location.module_label,
        },
        "nearby_names": names[:20],
    }


def format_hex_dump(data: bytes, base_address: int, *, highlight: tuple[int, int] | None = None) -> str:
    lines: list[str] = []
    for row in range(0, min(len(data), 256), 16):
        chunk = data[row : row + 16]
        hex_part = " ".join(f"{byte:02X}" for byte in chunk)
        ascii_part = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in chunk)
        addr = base_address + row
        marker = ""
        if highlight is not None:
            start, end = highlight
            if start <= addr < end:
                marker = "  <--"
        lines.append(f"{addr:016X}  {hex_part:<47}  {ascii_part}{marker}")
    return "\n".join(lines)


def watch_address(
    process_handle,
    address: int,
    *,
    size: int = 128,
    interval_sec: float = 1.0,
    duration_sec: float = 30.0,
    on_sample: Any | None = None,
) -> list[dict[str, Any]]:
    """Poll memory and record handle/name changes (for CE-style observation)."""
    samples: list[dict[str, Any]] = []
    deadline = time.time() + duration_sec
    previous: bytes | None = None
    while time.time() < deadline:
        data = _read_memory(process_handle, address, size) or b""
        handles = [
            handle
            for _offset, handle, _enc in extract_handle_hits(data, base_offset=0)
        ]
        names = [decoded.text for decoded in scan_utf16le_null_strings(data)]
        changed = previous is not None and data != previous
        sample = {
            "time": time.time(),
            "address": hex(address),
            "changed": changed,
            "handles": handles,
            "utf16_names": names[:10],
            "hex_preview": data[:64].hex(),
        }
        samples.append(sample)
        if on_sample:
            on_sample(sample)
        previous = data
        time.sleep(interval_sec)
    return samples


@dataclass
class StandaloneHit:
    """A handle or nickname found in memory without requiring local pairing."""

    address: int
    strategy: str
    encoding: str
    location: MemoryLocation
    lobby_score: float
    region_type: str
    score_notes: list[str] = field(default_factory=list)

    def summary_line(self) -> str:
        return (
            f"  @ 0x{self.address:X} [{self.strategy}] "
            f"({self.location.module_label}, {self.region_type}) "
            f"评分 {self.lobby_score:.0f}"
        )


@dataclass
class PairVerificationMatch:
    """One name↔handle association candidate for a known player pair."""

    name_address: int
    handle_address: int
    offset_name_to_handle: int
    lobby_score: float
    confirmed: bool
    match_source: str
    location: MemoryLocation
    name_encoding: str = ""
    handle_encoding: str = ""
    name_strategy: str = ""
    handle_strategy: str = ""
    score_notes: list[str] = field(default_factory=list)

    def summary_line(self) -> str:
        flag = "✓ 确认" if self.confirmed else "○ 候选"
        enc = f"名={self.name_strategy or self.name_encoding}|柄={self.handle_strategy or self.handle_encoding}"
        return (
            f"{flag} [{self.match_source}] 评分 {self.lobby_score:.0f} | "
            f"{enc} | "
            f"昵称 @ 0x{self.name_address:X} ({self.location.module_label}) | "
            f"句柄 @ 0x{self.handle_address:X} (offset {self.offset_name_to_handle:+d}) | "
            f"{'; '.join(self.score_notes[:2])}"
        )


@dataclass
class PairVerificationReport:
    expected_handle: str
    expected_name: str
    matches: list[PairVerificationMatch] = field(default_factory=list)
    confirmed_count: int = 0
    scan_stats: ComprehensiveScanStats | None = None
    standalone_names: list[StandaloneHit] = field(default_factory=list)
    standalone_handles: list[StandaloneHit] = field(default_factory=list)
    local_pair_count: int = 0
    remote_pair_count: int = 0
    host_anchor: HostHandleAnchor | None = None
    host_vicinity_handles: list[str] = field(default_factory=list)

    def best_confirmed(self) -> PairVerificationMatch | None:
        confirmed = [item for item in self.matches if item.confirmed]
        if not confirmed:
            return None
        return max(confirmed, key=lambda item: item.lobby_score)

    def discovery_summary_lines(self) -> list[str]:
        lines = [
            f"独立昵称命中: {len(self.standalone_names)} 处",
            f"独立句柄命中: {len(self.standalone_handles)} 处",
            f"邻近配对: {self.local_pair_count} 条, 远程配对: {self.remote_pair_count} 条",
        ]
        if self.host_anchor is not None:
            lines.append(f"--- 主机锚点 ---")
            lines.append(self.host_anchor.summary_line())
            if self.host_vicinity_handles:
                preview = ", ".join(self.host_vicinity_handles[:8])
                suffix = " ..." if len(self.host_vicinity_handles) > 8 else ""
                lines.append(
                    f"模块邻域句柄 ({len(self.host_vicinity_handles)}): {preview}{suffix}"
                )
        if self.standalone_names:
            lines.append("--- 昵称地址 (按评分) ---")
            for hit in self.standalone_names[:10]:
                lines.append(hit.summary_line())
        if self.standalone_handles:
            lines.append("--- 句柄地址 (按评分) ---")
            for hit in self.standalone_handles[:10]:
                lines.append(hit.summary_line())
        if (
            self.standalone_names
            and self.standalone_handles
            and self.local_pair_count == 0
            and self.remote_pair_count == 0
        ):
            lines.append(
                "提示: 昵称与句柄可能分属不同内存区域（非 768B 邻近），"
                "SC2 常将二者分开存储。"
            )
        return lines

    def stats_summary_lines(self) -> list[str]:
        if self.scan_stats is None:
            return []
        lines = ["--- 扫描策略统计 ---"]
        if self.scan_stats.name_hits:
            parts = [f"{key}={count}" for key, count in sorted(self.scan_stats.name_hits.items())]
            lines.append("昵称命中: " + ", ".join(parts))
        if self.scan_stats.handle_hits:
            parts = [f"{key}={count}" for key, count in sorted(self.scan_stats.handle_hits.items())]
            lines.append("句柄命中: " + ", ".join(parts))
        lines.append(f"配对尝试: {self.scan_stats.pair_attempts}")
        return lines


def _name_matches_expected(text: str, expected: str) -> bool:
    return text.strip() == expected.strip()


def _score_handle_location(location: MemoryLocation) -> tuple[float, list[str]]:
    score = 0.0
    notes: list[str] = []
    if location.region_type == "private":
        score += 40.0
        notes.append("private heap (+40)")
    elif location.region_type == "mapped":
        score += 20.0
        notes.append("mapped (+20)")
    elif location.region_type == "image":
        score -= 30.0
        notes.append("module image (-30)")
    if location.module_name and location.module_name.lower().startswith("sc2"):
        if location.region_type == "image":
            score -= 20.0
            notes.append("SC2.exe static (-20)")
    if location.protect in {0x04, 0x40, 0x80}:
        score += 15.0
        notes.append("writable (+15)")
    return score, notes


def _seed_handle_hits_from_host_anchor(
    process_handle,
    *,
    modules: list[ModuleInfo],
    expected_handle: str,
    strategies: ScanStrategies,
    handle_hits: list[DecodedHandleHit],
) -> tuple[HostHandleAnchor | None, list[str]]:
    if not strategies.use_host_anchor:
        return None, []

    anchor = read_host_handle_anchor(
        process_handle,
        modules,
        offset=strategies.host_handle_module_offset,
    )
    if anchor is None:
        return None, []

    vicinity = scan_module_vicinity_handles(
        process_handle,
        anchor,
        modules,
        radius=strategies.host_anchor_scan_radius,
    )
    vicinity_handles = [item.handle for item in vicinity]
    known_addresses = {hit.address for hit in handle_hits}

    for vhit in vicinity:
        if vhit.handle != expected_handle:
            continue
        if vhit.address in known_addresses:
            continue
        handle_hits.append(
            DecodedHandleHit(
                address=vhit.address,
                handle=vhit.handle,
                encoding=vhit.encoding,
                strategy="host_anchor_vicinity",
                exact=True,
            )
        )
        known_addresses.add(vhit.address)

    if anchor.handle == expected_handle and anchor.handle_address not in known_addresses:
        handle_hits.append(
            DecodedHandleHit(
                address=anchor.handle_address,
                handle=anchor.handle,
                encoding=anchor.encoding,
                strategy="host_anchor_direct",
                exact=True,
            )
        )

    return anchor, vicinity_handles


def _seed_handle_hits_from_lobby_struct(
    process_handle,
    *,
    expected_handle: str,
    strategies: ScanStrategies,
    handle_hits: list[DecodedHandleHit],
) -> None:
    if not strategies.use_lobby_member_struct:
        return
    known = {hit.address for hit in handle_hits}
    for address in scan_process_for_lobby_profile_handle(
        process_handle,
        expected_handle,
        time_budget_sec=5.0,
    ):
        if address in known:
            continue
        if not verify_lobby_profile_id_at(process_handle, address, expected_handle):
            continue
        handle_hits.append(
            DecodedHandleHit(
                address=address,
                handle=expected_handle,
                encoding="profile_triplet",
                strategy="lobby_member_struct",
                exact=True,
            )
        )
        known.add(address)


def _boost_standalone_with_host_anchor(
    process_handle,
    *,
    modules: list[ModuleInfo],
    expected_handle: str,
    strategies: ScanStrategies,
    standalone_handles: list[StandaloneHit],
    anchor: HostHandleAnchor | None,
) -> None:
    if anchor is None or not strategies.use_host_anchor:
        return

    vicinity = scan_module_vicinity_handles(
        process_handle,
        anchor,
        modules,
        radius=strategies.host_anchor_scan_radius,
    )
    existing_standalone = {hit.address for hit in standalone_handles}
    for vhit in vicinity:
        if vhit.handle != expected_handle:
            continue
        if vhit.address in existing_standalone:
            continue
        location = locate_address(
            vhit.address,
            modules=modules,
            process_handle=process_handle,
        )
        score, notes = _score_handle_location(location)
        bonus, anchor_notes = anchor_proximity_bonus(
            vhit.address,
            anchor,
            radius=strategies.host_anchor_scan_radius,
        )
        standalone_handles.append(
            StandaloneHit(
                address=vhit.address,
                strategy="host_anchor_vicinity",
                encoding=vhit.encoding,
                location=location,
                lobby_score=score + bonus + 25.0,
                region_type=location.region_type,
                score_notes=notes + anchor_notes + ["host anchor scan (+25)"],
            )
        )
        existing_standalone.add(vhit.address)

    if anchor.handle == expected_handle and anchor.handle_address not in existing_standalone:
        location = locate_address(
            anchor.handle_address,
            modules=modules,
            process_handle=process_handle,
        )
        score, notes = _score_handle_location(location)
        bonus, anchor_notes = anchor_proximity_bonus(
            anchor.handle_address,
            anchor,
            radius=strategies.host_anchor_scan_radius,
        )
        standalone_handles.append(
            StandaloneHit(
                address=anchor.handle_address,
                strategy="host_anchor_direct",
                encoding=anchor.encoding,
                location=location,
                lobby_score=score + bonus + 45.0,
                region_type=location.region_type,
                score_notes=notes + anchor_notes + ["host anchor direct (+45)"],
            )
        )

    for hit in standalone_handles:
        bonus, notes = anchor_proximity_bonus(
            hit.address,
            anchor,
            radius=strategies.host_anchor_scan_radius,
        )
        if bonus:
            hit.lobby_score += bonus
            hit.score_notes.extend(notes)

    standalone_handles.sort(key=lambda item: item.lobby_score, reverse=True)


def _build_standalone_hits(
    process_handle,
    *,
    pid: int,
    name_hits: list,
    handle_hits: list,
    expected_name: str,
    strategies: ScanStrategies,
) -> tuple[list[StandaloneHit], list[StandaloneHit]]:
    modules = build_module_map(pid)
    names: list[StandaloneHit] = []
    handles: list[StandaloneHit] = []

    for hit in name_hits:
        location = locate_address(
            hit.address,
            modules=modules,
            process_handle=process_handle,
        )
        probe = score_name_probe(
            NameProbeResult(
                name=expected_name,
                name_address=hit.address,
                name_encoding=hit.encoding,
                location=location,
                handles=[],
            )
        )
        names.append(
            StandaloneHit(
                address=hit.address,
                strategy=hit.strategy,
                encoding=hit.encoding,
                location=location,
                lobby_score=probe.lobby_score,
                region_type=location.region_type,
                score_notes=list(probe.score_notes),
            )
        )

    for hit in handle_hits:
        location = locate_address(
            hit.address,
            modules=modules,
            process_handle=process_handle,
        )
        score, notes = _score_handle_location(location)
        handles.append(
            StandaloneHit(
                address=hit.address,
                strategy=hit.strategy,
                encoding=hit.encoding,
                location=location,
                lobby_score=score,
                region_type=location.region_type,
                score_notes=notes,
            )
        )

    if strategies.prefer_private_heap:
        private_names = [item for item in names if item.region_type == "private"]
        private_handles = [item for item in handles if item.region_type == "private"]
        if private_names:
            names = private_names + [item for item in names if item.region_type != "private"]
        if private_handles:
            handles = private_handles + [
                item for item in handles if item.region_type != "private"
            ]

    names.sort(key=lambda item: item.lobby_score, reverse=True)
    handles.sort(key=lambda item: item.lobby_score, reverse=True)
    return names, handles


def _pick_remote_pair_with_rosters(
    process_handle,
    *,
    pid: int,
    expected_name: str,
    expected_handle: str,
    standalone_names: list[StandaloneHit],
    standalone_handles: list[StandaloneHit],
    strategies: ScanStrategies,
    modules: list[ModuleInfo],
    room_member_handles: set[str] | None = None,
) -> PairVerificationMatch | None:
    if not strategies.allow_remote_pairing:
        return None

    known = set(room_member_handles or set())
    known.add(expected_handle)
    if strategies.use_host_anchor:
        anchor = read_host_handle_anchor(
            process_handle,
            modules,
            offset=strategies.host_handle_module_offset,
        )
        if anchor is not None:
            known.add(anchor.handle)
    clusters = []
    if strategies.use_channel_roster:
        clusters = scan_channel_rosters(
            process_handle,
            known_handles=known,
            min_members=strategies.channel_roster_min_members,
            max_span=strategies.channel_roster_max_span,
            time_budget_sec=6.0,
            use_lobby_member_struct=strategies.use_lobby_member_struct,
            lobby_member_max_slots=strategies.lobby_member_max_slots,
        )
        target_clusters = [c for c in clusters if c.contains_handle(expected_handle)]

        for cluster in target_clusters:
            handle_addr = pick_handle_address_in_cluster(cluster, expected_handle)
            if handle_addr is None:
                continue
            handle_ok = verify_handle_bytes_at(
                process_handle, handle_addr, expected_handle, encoding="ascii_z"
            ) or verify_lobby_profile_id_at(
                process_handle, handle_addr, expected_handle
            )
            if not handle_ok:
                continue
            name_addr = pick_name_in_roster_window(
                process_handle, cluster, expected_name
            )
            if name_addr is None:
                for hit in standalone_names:
                    if cluster.contains_address(hit.address) and verify_name_bytes_at(
                        process_handle,
                        hit.address,
                        expected_name,
                        encoding="utf16_le_z",
                    ):
                        name_addr = hit.address
                        break
            if name_addr is None:
                continue
            name_ok = verify_name_bytes_at(
                process_handle, name_addr, expected_name, encoding="utf16_le_z"
            ) or verify_lobby_name_utf8_at(
                process_handle, name_addr, expected_name
            )
            if not name_ok:
                continue
            handle_strategy = "channel_roster"
            if "lobby_member_struct" in cluster.notes:
                handle_strategy = "lobby_member_struct"
            handle_hit = next(
                (h for h in standalone_handles if h.address == handle_addr),
                StandaloneHit(
                    address=handle_addr,
                    strategy=handle_strategy,
                    encoding="profile_triplet"
                    if handle_strategy == "lobby_member_struct"
                    else "ascii_z",
                    location=locate_address(
                        handle_addr, modules=modules, process_handle=process_handle
                    ),
                    lobby_score=60.0,
                    region_type=cluster.region_type,
                ),
            )
            name_hit = next(
                (n for n in standalone_names if n.address == name_addr),
                StandaloneHit(
                    address=name_addr,
                    strategy=handle_strategy,
                    encoding="utf8_z"
                    if verify_lobby_name_utf8_at(
                        process_handle, name_addr, expected_name
                    )
                    else "utf16_le_z",
                    location=locate_address(
                        name_addr, modules=modules, process_handle=process_handle
                    ),
                    lobby_score=60.0,
                    region_type=cluster.region_type,
                ),
            )
            remote = _build_remote_pair(
                best_name=name_hit,
                best_handle=handle_hit,
                expected_name=expected_name,
                expected_handle=expected_handle,
            )
            remote.match_source = f"{handle_strategy}/{cluster.member_count}p"
            if handle_strategy == "lobby_member_struct":
                remote.score_notes.append(
                    f"Lobby struct roster stride 0x{strategies.lobby_member_record_size:X}"
                )
            else:
                remote.score_notes.append(f"频道 roster {cluster.member_count} 成员")
            remote.lobby_score += 40.0
            if handle_strategy == "lobby_member_struct":
                remote.lobby_score += 25.0
            return remote

    if not standalone_names or not standalone_handles:
        return None

    for name_hit in standalone_names:
        if name_hit.region_type == "image":
            continue
        if not verify_name_bytes_at(
            process_handle,
            name_hit.address,
            expected_name,
            encoding="utf16_le_z",
        ):
            continue
        for handle_hit in standalone_handles:
            if handle_hit.region_type == "image":
                continue
            if not verify_handle_bytes_at(
                process_handle,
                handle_hit.address,
                expected_handle,
                encoding="ascii_z",
            ):
                continue
            return _build_remote_pair(
                best_name=name_hit,
                best_handle=handle_hit,
                expected_name=expected_name,
                expected_handle=expected_handle,
            )
    return None


def _build_remote_pair(
    *,
    best_name: StandaloneHit,
    best_handle: StandaloneHit,
    expected_name: str,
    expected_handle: str,
) -> PairVerificationMatch:
    distance = best_handle.address - best_name.address
    notes = [
        f"远程存储，相距 {distance:+d} 字节",
        f"昵称: {best_name.location.module_label}",
        f"句柄: {best_handle.location.module_label}",
    ]
    score = (best_name.lobby_score + best_handle.lobby_score) / 2.0
    if best_name.region_type == "private" and best_handle.region_type == "private":
        score += 25.0
        notes.append("双方均在 private heap (+25)")
    return PairVerificationMatch(
        name_address=best_name.address,
        handle_address=best_handle.address,
        offset_name_to_handle=distance,
        lobby_score=score,
        confirmed=True,
        match_source="remote_heuristic",
        location=best_name.location,
        name_encoding=best_name.encoding,
        handle_encoding=best_handle.encoding,
        name_strategy=best_name.strategy,
        handle_strategy=best_handle.strategy,
        score_notes=notes,
    )


def _store_pair_match(
    matches: dict[tuple[int, int], PairVerificationMatch],
    *,
    name_address: int,
    handle_address: int,
    expected_name: str,
    expected_handle: str,
    match_source: str,
    location: MemoryLocation,
    name_encoding: str,
    handle_encoding: str,
    name_strategy: str,
    handle_strategy: str,
    score_notes: list[str],
    lobby_score: float,
    stats: ComprehensiveScanStats | None,
) -> None:
    if stats is not None:
        stats.pair_attempts += 1
    confirmed = True
    key = (name_address, handle_address)
    existing = matches.get(key)
    if existing is not None and lobby_score <= existing.lobby_score:
        return
    matches[key] = PairVerificationMatch(
        name_address=name_address,
        handle_address=handle_address,
        offset_name_to_handle=handle_address - name_address,
        lobby_score=lobby_score,
        confirmed=confirmed,
        match_source=match_source,
        location=location,
        name_encoding=name_encoding,
        handle_encoding=handle_encoding,
        name_strategy=name_strategy,
        handle_strategy=handle_strategy,
        score_notes=score_notes,
    )


def verify_player_pair(
    process_handle,
    *,
    pid: int,
    expected_handle: str,
    expected_name: str,
    radius: int = 768,
    time_budget_sec: float = 45.0,
    strategies: ScanStrategies | None = None,
) -> PairVerificationReport:
    """Mode 1: multi-strategy scan — standalone discovery + local/remote pairing."""
    active = strategies or DEFAULT_SCAN_STRATEGIES
    stats = ComprehensiveScanStats()
    modules = build_module_map(pid)
    matches: dict[tuple[int, int], PairVerificationMatch] = {}
    scan_fn = make_scan_bytes_fn(active)

    name_budget = time_budget_sec * 0.5
    handle_budget = time_budget_sec * 0.5

    name_hits = scan_process_for_decoded_strings(
        process_handle,
        expected_name,
        scan_fn,
        strategies=active,
        time_budget_sec=name_budget,
        max_hits=120,
        stats=stats,
    )
    handle_hits = scan_process_for_decoded_handles(
        process_handle,
        expected_handle,
        scan_fn,
        strategies=active,
        time_budget_sec=handle_budget,
        max_hits=120,
        stats=stats,
    )
    host_anchor, host_vicinity_handles = _seed_handle_hits_from_host_anchor(
        process_handle,
        modules=modules,
        expected_handle=expected_handle,
        strategies=active,
        handle_hits=handle_hits,
    )
    _seed_handle_hits_from_lobby_struct(
        process_handle,
        expected_handle=expected_handle,
        strategies=active,
        handle_hits=handle_hits,
    )
    standalone_names, standalone_handles = _build_standalone_hits(
        process_handle,
        pid=pid,
        name_hits=name_hits,
        handle_hits=handle_hits,
        expected_name=expected_name,
        strategies=active,
    )
    _boost_standalone_with_host_anchor(
        process_handle,
        modules=modules,
        expected_handle=expected_handle,
        strategies=active,
        standalone_handles=standalone_handles,
        anchor=host_anchor,
    )
    local_pair_count = 0

    for name_hit in name_hits:
        window_base = max(0, name_hit.address - radius)
        data = _read_memory(process_handle, window_base, radius * 2) or b""
        handle_near = collect_handles_in_window(
            data,
            window_base=window_base,
            anchor_address=name_hit.address,
            expected_handle=expected_handle,
            strategies=active,
            stats=stats,
        )
        if not handle_near:
            continue
        location = locate_address(
            name_hit.address,
            modules=modules,
            process_handle=process_handle,
        )
        probe = score_name_probe(
            NameProbeResult(
                name=expected_name,
                name_address=name_hit.address,
                name_encoding=name_hit.encoding,
                location=location,
                handles=[
                    HandleNearName(
                        handle=item.handle,
                        handle_address=item.address,
                        offset_from_name=item.address - name_hit.address,
                        encoding=item.encoding,
                    )
                    for item in handle_near[:3]
                ],
            )
        )
        best_handle = handle_near[0]
        local_pair_count += 1
        _store_pair_match(
            matches,
            name_address=name_hit.address,
            handle_address=best_handle.address,
            expected_name=expected_name,
            expected_handle=expected_handle,
            match_source=f"local/name→handle/{name_hit.strategy}+{best_handle.strategy}",
            location=location,
            name_encoding=name_hit.encoding,
            handle_encoding=best_handle.encoding,
            name_strategy=name_hit.strategy,
            handle_strategy=best_handle.strategy,
            score_notes=list(probe.score_notes),
            lobby_score=probe.lobby_score + 55.0,
            stats=stats,
        )

    for handle_hit in handle_hits:
        window_base = max(0, handle_hit.address - radius)
        data = _read_memory(process_handle, window_base, radius * 2) or b""
        names_near = collect_names_in_window(
            data,
            window_base=window_base,
            anchor_address=handle_hit.address,
            expected_name=expected_name,
            strategies=active,
            stats=stats,
        )
        if not names_near:
            continue
        best_name = names_near[0]
        location = locate_address(
            best_name.address,
            modules=modules,
            process_handle=process_handle,
        )
        offset = handle_hit.address - best_name.address
        probe = score_name_probe(
            NameProbeResult(
                name=expected_name,
                name_address=best_name.address,
                name_encoding=best_name.encoding,
                location=location,
                handles=[
                    HandleNearName(
                        handle=handle_hit.handle,
                        handle_address=handle_hit.address,
                        offset_from_name=offset,
                        encoding=handle_hit.encoding,
                    )
                ],
            )
        )
        local_pair_count += 1
        _store_pair_match(
            matches,
            name_address=best_name.address,
            handle_address=handle_hit.address,
            expected_name=expected_name,
            expected_handle=expected_handle,
            match_source=f"local/handle→name/{handle_hit.strategy}+{best_name.strategy}",
            location=location,
            name_encoding=best_name.encoding,
            handle_encoding=handle_hit.encoding,
            name_strategy=best_name.strategy,
            handle_strategy=handle_hit.strategy,
            score_notes=list(probe.score_notes),
            lobby_score=probe.lobby_score + 60.0,
            stats=stats,
        )

    remote_pair_count = 0
    if active.allow_remote_pairing and standalone_names and standalone_handles and not matches:
        remote = _pick_remote_pair_with_rosters(
            process_handle,
            pid=pid,
            expected_name=expected_name,
            expected_handle=expected_handle,
            standalone_names=standalone_names,
            standalone_handles=standalone_handles,
            strategies=active,
            modules=modules,
        )
        if remote is not None:
            matches[(remote.name_address, remote.handle_address)] = remote
            remote_pair_count = 1

    ordered = sorted(matches.values(), key=lambda item: item.lobby_score, reverse=True)
    return PairVerificationReport(
        expected_handle=expected_handle,
        expected_name=expected_name,
        matches=ordered,
        confirmed_count=sum(1 for item in ordered if item.confirmed),
        scan_stats=stats,
        standalone_names=standalone_names,
        standalone_handles=standalone_handles,
        local_pair_count=local_pair_count,
        remote_pair_count=remote_pair_count,
        host_anchor=host_anchor,
        host_vicinity_handles=host_vicinity_handles,
    )


@dataclass
class MonitorSnapshot:
    phase: str
    timestamp: float
    name_addresses: set[int]
    handle_addresses: set[int]
    pair_candidates: list[PairVerificationMatch]


@dataclass
class MonitorTickEvent:
    phase: str
    new_name_addresses: list[int]
    new_handle_addresses: list[int]
    new_pairs: list[PairVerificationMatch]
    message: str


class PairMonitorSession:
    """Mode 2: monitor before/after entering lobby for the same handle+name pair."""

    def __init__(
        self,
        process_handle,
        *,
        pid: int,
        expected_handle: str,
        expected_name: str,
        radius: int = 768,
        strategies: ScanStrategies | None = None,
    ) -> None:
        self._process = process_handle
        self._pid = pid
        self.expected_handle = expected_handle.strip()
        self.expected_name = expected_name.strip()
        self.radius = radius
        self.strategies = strategies or DEFAULT_SCAN_STRATEGIES
        self._stats = ComprehensiveScanStats()
        self.phase = "baseline"
        self.started_at = time.time()
        self.baseline: MonitorSnapshot | None = None
        self.in_lobby: MonitorSnapshot | None = None
        self._all_name_addrs: set[int] = set()
        self._all_handle_addrs: set[int] = set()
        self.events: list[MonitorTickEvent] = []

    def _scan_addresses(self) -> tuple[set[int], set[int]]:
        scan_fn = make_scan_bytes_fn(self.strategies)
        name_hits = scan_process_for_decoded_strings(
            self._process,
            self.expected_name,
            scan_fn,
            strategies=self.strategies,
            time_budget_sec=8.0,
            max_hits=80,
            stats=self._stats,
        )
        handle_hits = scan_process_for_decoded_handles(
            self._process,
            self.expected_handle,
            scan_fn,
            strategies=self.strategies,
            time_budget_sec=8.0,
            max_hits=80,
            stats=self._stats,
        )
        return {item.address for item in name_hits}, {item.address for item in handle_hits}

    def _remote_pair_from_addresses(
        self,
        name_addrs: set[int],
        handle_addrs: set[int],
    ) -> PairVerificationMatch | None:
        if not self.strategies.allow_remote_pairing or not name_addrs or not handle_addrs:
            return None
        modules = build_module_map(self._pid)
        scored_names: list[StandaloneHit] = []
        scored_handles: list[StandaloneHit] = []
        for address in name_addrs:
            location = locate_address(
                address,
                modules=modules,
                process_handle=self._process,
            )
            probe = score_name_probe(
                NameProbeResult(
                    name=self.expected_name,
                    name_address=address,
                    name_encoding="utf16_le_z",
                    location=location,
                    handles=[],
                )
            )
            scored_names.append(
                StandaloneHit(
                    address=address,
                    strategy="monitor",
                    encoding="utf16_le_z",
                    location=location,
                    lobby_score=probe.lobby_score,
                    region_type=location.region_type,
                    score_notes=list(probe.score_notes),
                )
            )
        for address in handle_addrs:
            location = locate_address(
                address,
                modules=modules,
                process_handle=self._process,
            )
            score, notes = _score_handle_location(location)
            scored_handles.append(
                StandaloneHit(
                    address=address,
                    strategy="monitor",
                    encoding="ascii_z",
                    location=location,
                    lobby_score=score,
                    region_type=location.region_type,
                    score_notes=notes,
                )
            )
        if self.strategies.prefer_private_heap:
            priv_names = [item for item in scored_names if item.region_type == "private"]
            priv_handles = [item for item in scored_handles if item.region_type == "private"]
            if priv_names:
                scored_names = priv_names
            if priv_handles:
                scored_handles = priv_handles
        if not scored_names or not scored_handles:
            return None
        scored_names.sort(key=lambda item: item.lobby_score, reverse=True)
        scored_handles.sort(key=lambda item: item.lobby_score, reverse=True)
        remote = _build_remote_pair(
            best_name=scored_names[0],
            best_handle=scored_handles[0],
            expected_name=self.expected_name,
            expected_handle=self.expected_handle,
        )
        remote.match_source = f"monitor_{self.phase}/remote_heuristic"
        return remote

    def _pairs_from_new_names(self, name_addrs: set[int]) -> list[PairVerificationMatch]:
        modules = build_module_map(self._pid)
        pairs: list[PairVerificationMatch] = []
        for name_address in sorted(name_addrs):
            window_base = max(0, name_address - self.radius)
            data = _read_memory(self._process, window_base, self.radius * 2) or b""
            handle_near = collect_handles_in_window(
                data,
                window_base=window_base,
                anchor_address=name_address,
                expected_handle=self.expected_handle,
                strategies=self.strategies,
                stats=self._stats,
            )
            if not handle_near:
                continue
            location = locate_address(
                name_address,
                modules=modules,
                process_handle=self._process,
            )
            best = handle_near[0]
            probe = score_name_probe(
                NameProbeResult(
                    name=self.expected_name,
                    name_address=name_address,
                    name_encoding="utf16_le_z",
                    location=location,
                    handles=[
                        HandleNearName(
                            handle=best.handle,
                            handle_address=best.address,
                            offset_from_name=best.address - name_address,
                            encoding=best.encoding,
                        )
                    ],
                )
            )
            pairs.append(
                PairVerificationMatch(
                    name_address=name_address,
                    handle_address=best.address,
                    offset_name_to_handle=best.address - name_address,
                    lobby_score=probe.lobby_score + 40.0,
                    confirmed=True,
                    match_source=f"monitor_{self.phase}/{best.strategy}",
                    location=location,
                    name_encoding="",
                    handle_encoding=best.encoding,
                    handle_strategy=best.strategy,
                    score_notes=list(probe.score_notes),
                )
            )
        pairs.sort(key=lambda item: item.lobby_score, reverse=True)
        return pairs

    def stats_summary_lines(self) -> list[str]:
        lines = ["--- 监控策略统计 ---"]
        if self._stats.name_hits:
            parts = [f"{k}={v}" for k, v in sorted(self._stats.name_hits.items())]
            lines.append("昵称: " + ", ".join(parts))
        if self._stats.handle_hits:
            parts = [f"{k}={v}" for k, v in sorted(self._stats.handle_hits.items())]
            lines.append("句柄: " + ", ".join(parts))
        return lines

    def tick(self) -> MonitorTickEvent:
        name_addrs, handle_addrs = self._scan_addresses()
        prev_names = set(self._all_name_addrs)
        prev_handles = set(self._all_handle_addrs)
        self._all_name_addrs |= name_addrs
        self._all_handle_addrs |= handle_addrs

        new_names = sorted(name_addrs - prev_names)
        new_handles = sorted(handle_addrs - prev_handles)
        new_pairs = self._pairs_from_new_names(set(new_names))

        if self.phase == "baseline" and self.baseline is None:
            self.baseline = MonitorSnapshot(
                phase="baseline",
                timestamp=time.time(),
                name_addresses=set(name_addrs),
                handle_addresses=set(handle_addrs),
                pair_candidates=self._pairs_from_new_names(name_addrs),
            )

        if self.phase == "in_lobby":
            assert self.baseline is not None
            lobby_new_names = name_addrs - self.baseline.name_addresses
            lobby_new_handles = handle_addrs - self.baseline.handle_addresses
            new_pairs = self._pairs_from_new_names(lobby_new_names)
            if not new_pairs and lobby_new_names and lobby_new_handles:
                remote = self._remote_pair_from_addresses(
                    lobby_new_names,
                    lobby_new_handles,
                )
                if remote is not None:
                    new_pairs = [remote]
            self.in_lobby = MonitorSnapshot(
                phase="in_lobby",
                timestamp=time.time(),
                name_addresses=set(name_addrs),
                handle_addresses=set(handle_addrs),
                pair_candidates=new_pairs,
            )
            message = (
                f"大厅内新增: 昵称 {len(lobby_new_names)} 处, "
                f"句柄 {len(lobby_new_handles)} 处, 配对 {len(new_pairs)} 条"
            )
        else:
            message = (
                f"基线采样: 昵称 {len(name_addrs)} 处, 句柄 {len(handle_addrs)} 处"
            )

        event = MonitorTickEvent(
            phase=self.phase,
            new_name_addresses=new_names,
            new_handle_addresses=new_handles,
            new_pairs=new_pairs,
            message=message,
        )
        self.events.append(event)
        return event

    def mark_in_lobby(self) -> None:
        self.phase = "in_lobby"
        if self.baseline is None:
            name_addrs, handle_addrs = self._scan_addresses()
            self.baseline = MonitorSnapshot(
                phase="baseline",
                timestamp=time.time(),
                name_addresses=set(name_addrs),
                handle_addresses=set(handle_addrs),
                pair_candidates=[],
            )


def compare_scan_and_monitor(
    scan_report: PairVerificationReport,
    monitor: PairMonitorSession,
) -> list[str]:
    """Compare mode 1 scan vs mode 2 monitor results."""
    lines: list[str] = []
    lines.append("=== 模式对比：扫描确认 vs 监控对比 ===")
    lines.append(
        f"扫描模式: 共 {len(scan_report.matches)} 条, "
        f"确认 {scan_report.confirmed_count} 条"
    )
    best = scan_report.best_confirmed()
    if best:
        lines.append(f"扫描最佳: {best.summary_line()}")

    if monitor.baseline:
        lines.append(
            f"监控基线: 昵称 {len(monitor.baseline.name_addresses)} 处, "
            f"句柄 {len(monitor.baseline.handle_addresses)} 处"
        )
    if monitor.in_lobby:
        lines.append(
            f"进入大厅后: 昵称 {len(monitor.in_lobby.name_addresses)} 处, "
            f"句柄 {len(monitor.in_lobby.handle_addresses)} 处, "
            f"新配对 {len(monitor.in_lobby.pair_candidates)} 条"
        )
        for pair in monitor.in_lobby.pair_candidates[:5]:
            lines.append(f"  监控配对: {pair.summary_line()}")

    if best and monitor.in_lobby:
        for pair in monitor.in_lobby.pair_candidates:
            if (
                abs(pair.name_address - best.name_address) <= 64
                or abs(pair.handle_address - best.handle_address) <= 64
            ):
                lines.append(
                    f"  ★ 地址接近扫描最佳结果 (Δname="
                    f"{pair.name_address - best.name_address:+d}, "
                    f"Δhandle={pair.handle_address - best.handle_address:+d})"
                )
                break
        offset_scan = best.offset_name_to_handle
        monitor_offsets = [p.offset_name_to_handle for p in monitor.in_lobby.pair_candidates]
        if monitor_offsets:
            closest = min(monitor_offsets, key=lambda value: abs(value - offset_scan))
            lines.append(
                f"  偏移对比: 扫描 {offset_scan:+d} vs 监控最近 {closest:+d} "
                f"(差 {closest - offset_scan:+d})"
            )
    return lines


def attach_sc2_process(
    *,
    pid: int | None = None,
    window_title_contains: str = "StarCraft II",
    process_names: tuple[str, ...] | None = None,
) -> tuple[Any, int]:
    selected = pid or get_sc2_pid(
        window_title_contains=window_title_contains,
        process_names=process_names or ("SC2_x64.exe", "SC2.exe"),
    )
    if selected is None:
        raise RuntimeError("SC2 process not found")
    return open_process_for_read(selected), int(selected)
