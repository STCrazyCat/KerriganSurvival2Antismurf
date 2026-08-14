"""Read the SC2 module-anchored host handle (CE: ``SC2_x64.exe+0x3E2F340``).

The lobby host Battle.net handle is stored at a stable offset inside the main
executable image. Use it to infer the local host identity and to scan the
nearby module data table for co-located lobby member handles before falling
back to full-process heap scans.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from antismurf.lobby.memory_formats import (
    StringEncoding,
    extract_handle_hits,
    extract_profile_triplets,
    handle_from_triplet,
)
from antismurf.lobby.memory_reader import _read_memory
from antismurf.models.player import is_valid_handle

DEFAULT_SC2_MODULE_NAMES: tuple[str, ...] = ("SC2_x64.exe", "SC2.exe")
DEFAULT_HOST_HANDLE_MODULE_OFFSET = 0x3E2F340
DEFAULT_HOST_ANCHOR_WINDOW = 256
DEFAULT_HOST_ANCHOR_VICINITY_RADIUS = 8192


@dataclass(frozen=True)
class HostHandleAnchor:
    module_name: str
    module_base: int
    anchor_offset: int
    anchor_address: int
    handle: str
    handle_address: int
    encoding: str
    module_label: str

    def summary_line(self) -> str:
        return (
            f"主机锚点 {self.module_label} → {self.handle} "
            f"@ 0x{self.handle_address:X} ({self.encoding})"
        )


@dataclass(frozen=True)
class VicinityHandleHit:
    address: int
    handle: str
    encoding: str
    offset_from_anchor: int


@dataclass(frozen=True)
class SniffedHandleCandidate:
    """A handle storage candidate found near the host anchor, with nearby
    storage interpretation used to confirm whether it is a real lobby player
    handle (not a random string in module data)."""

    handle: str
    address: int
    encoding: str
    offset_from_anchor: int
    nearby_profile_id: int | None = None
    nearby_name: str | None = None
    struct_header_ok: bool = False
    score: float = 0.0
    evidence: tuple[str, ...] = ()

    def summary_line(self) -> str:
        bits = [f"score={self.score:.0f}"]
        if self.nearby_profile_id is not None:
            bits.append(f"profile_id={self.nearby_profile_id}")
        if self.nearby_name:
            bits.append(f"name={self.nearby_name!r}")
        if self.struct_header_ok:
            bits.append("struct_header")
        return (
            f"{self.handle} @ 0x{self.address:X} ({self.encoding}, "
            f"Δ{self.offset_from_anchor:+d}) [{'|'.join(bits)}]"
        )


def _extract_nearby_ascii_name(
    data: bytes,
    rel_offset: int,
    *,
    window: int = 160,
) -> str | None:
    """Find a printable ASCII name near a handle candidate (ignoring the handle itself)."""
    start = max(0, rel_offset - window)
    end = min(len(data), rel_offset + window)
    chunk = data[start:end]
    best: str | None = None
    best_dist = window
    cursor = 0
    while cursor < len(chunk):
        if 0x21 <= chunk[cursor] <= 0x7E:
            j = cursor
            while j < len(chunk) and 0x21 <= chunk[j] <= 0x7E:
                j += 1
            text = chunk[cursor:j].decode("ascii", errors="ignore")
            if 3 <= len(text) <= 40 and not is_valid_handle(text):
                dist = abs((start + cursor) - rel_offset)
                if dist < best_dist:
                    best_dist = dist
                    best = text
            cursor = j
        else:
            cursor += 1
    return best


def _interpret_nearby_storage(
    data: bytes,
    rel_offset: int,
    handle: str,
) -> tuple[int | None, str | None, bool, list[str]]:
    """Interpret bytes near a handle candidate to confirm it is a lobby player
    handle storage: matching profile_id field, nearby display name, and/or a
    lobby member struct header (program == 0x5332) at offset -0x20."""
    evidence: list[str] = []
    nearby_profile_id: int | None = None
    try:
        profile_id = int(handle.rsplit("-", 1)[-1])
    except ValueError:
        profile_id = None

    struct_ok = False
    # 1) profile_id 字段:句柄尾部数字以 4 字节 LE 出现在 ±0x40 内
    if profile_id is not None:
        needle = struct.pack("<I", profile_id)
        search_start = max(0, rel_offset - 0x40)
        search_end = min(len(data) - 4, rel_offset + 0x40)
        if search_start <= search_end:
            found = data.find(needle, search_start, search_end + 4)
            if found >= 0:
                nearby_profile_id = profile_id
                evidence.append(f"profile_id 字段 @Δ{found - rel_offset:+d}")

    # 2) struct 头:handle 地址 -0x20 处 program == 0x5332
    header_rel = rel_offset - 0x20
    if header_rel >= 0 and header_rel + 0x18 <= len(data):
        program = struct.unpack_from("<I", data, header_rel + 0x14)[0]
        if program == 0x5332:
            struct_ok = True
            evidence.append("struct 头 program=0x5332")

    # 3) 附近显示名字
    name = _extract_nearby_ascii_name(data, rel_offset)
    if name:
        evidence.append(f"附近名字 {name!r}")

    return nearby_profile_id, name, struct_ok, evidence


def sniff_host_handle_storage(
    process_handle,
    modules,
    *,
    anchor_offset: int | str = DEFAULT_HOST_HANDLE_MODULE_OFFSET,
    radius: int = DEFAULT_HOST_ANCHOR_VICINITY_RADIUS,
    known_host_handle: str = "",
) -> list[SniffedHandleCandidate]:
    """Sniff multi-format handle storages near the host anchor and rank them by
    nearby-storage interpretation.  Returns candidates sorted by score desc.

    Covers the case where the fixed module offset moved after a game update:
    the host handle is still stored somewhere in the module table near the old
    anchor, and surrounding struct/profile/name bytes confirm which candidate is
    the real lobby host handle.
    """
    module = _find_sc2_module(modules, DEFAULT_SC2_MODULE_NAMES)
    if module is None:
        return []

    anchor_off = parse_module_offset(anchor_offset)
    if anchor_off < 0 or anchor_off >= module.size:
        return []
    anchor_address = module.base + anchor_off

    span_start = max(module.base, anchor_address - radius)
    span_end = min(module.base + module.size, anchor_address + radius)
    if span_end <= span_start:
        return []

    data = _read_memory(process_handle, span_start, span_end - span_start)
    if not data:
        return []

    candidates: dict[str, SniffedHandleCandidate] = {}

    def _add(handle: str, address: int, encoding: str) -> None:
        rel = address - span_start
        profile_id, name, struct_ok, evidence = _interpret_nearby_storage(
            data, rel, handle
        )
        distance = abs(address - anchor_address)
        if address == anchor_address:
            score = 100.0
            evidence = ["锚点原位命中"] + evidence
        elif distance <= 0x100:
            score = 60.0
            evidence = [f"距锚点 Δ{distance:+d}"] + evidence
        elif distance <= 0x1000:
            score = 35.0
            evidence = [f"模块表 Δ{distance:+d}"] + evidence
        else:
            score = 15.0
            evidence = [f"锚点邻近 Δ{distance:+d}"] + evidence
        if profile_id is not None:
            score += 40.0
        if struct_ok:
            score += 30.0
        if name:
            score += 20.0
        if known_host_handle and handle == known_host_handle:
            score += 50.0
            evidence = ["匹配已知主机句柄"] + evidence
        existing = candidates.get(handle)
        if existing is None or score > existing.score:
            candidates[handle] = SniffedHandleCandidate(
                handle=handle,
                address=address,
                encoding=encoding,
                offset_from_anchor=address - anchor_address,
                nearby_profile_id=profile_id,
                nearby_name=name,
                struct_header_ok=struct_ok,
                score=score,
                evidence=tuple(evidence),
            )

    for rel_offset, handle, _encoding in extract_handle_hits(data):
        _add(handle, span_start + rel_offset, StringEncoding.ASCII_Z.value)
    for triplet in extract_profile_triplets(data, base_offset=span_start):
        _add(handle_from_triplet(triplet), triplet.offset, "profile_triplet")

    return sorted(candidates.values(), key=lambda item: (-item.score, item.address))


def confirm_host_handle_via_sniff(
    process_handle,
    modules,
    *,
    anchor_offset: int | str = DEFAULT_HOST_HANDLE_MODULE_OFFSET,
    radius: int = DEFAULT_HOST_ANCHOR_VICINITY_RADIUS,
    min_score: float = 60.0,
) -> SniffedHandleCandidate | None:
    """Best-effort confirm a host handle by sniffing near the anchor."""
    candidates = sniff_host_handle_storage(
        process_handle,
        modules,
        anchor_offset=anchor_offset,
        radius=radius,
    )
    for candidate in candidates:
        if candidate.score >= min_score:
            return candidate
    return None


def parse_module_offset(value: int | str) -> int:
    if isinstance(value, str):
        return int(value.strip(), 0)
    return int(value)


def _find_sc2_module(modules, module_names: tuple[str, ...] = DEFAULT_SC2_MODULE_NAMES):
    lowered = {name.lower() for name in module_names}
    for module in modules:
        if module.name.lower() in lowered:
            return module
    for module in modules:
        if module.name.lower().startswith("sc2"):
            return module
    return None


def _decode_ascii_handle_at(data: bytes, base_address: int, rel_offset: int) -> tuple[str, int, str] | None:
    if rel_offset < 0 or rel_offset >= len(data):
        return None
    end = data.find(b"\x00", rel_offset)
    if end <= rel_offset:
        return None
    if end - rel_offset > 64:
        return None
    try:
        text = data[rel_offset:end].decode("ascii")
    except UnicodeDecodeError:
        return None
    if not is_valid_handle(text):
        return None
    return text, base_address + rel_offset, StringEncoding.ASCII_Z.value


def _decode_triplet_at(data: bytes, base_address: int, rel_offset: int) -> tuple[str, int, str] | None:
    if rel_offset < 0 or rel_offset + 16 > len(data):
        return None
    for triplet in extract_profile_triplets(data[rel_offset : rel_offset + 16], base_offset=0):
        if triplet.offset != 0:
            continue
        handle = handle_from_triplet(triplet)
        return handle, base_address + rel_offset, "profile_triplet"
    return None


def _decode_handle_near(
    data: bytes,
    base_address: int,
    anchor_rel: int,
    *,
    slack: int = 128,
) -> tuple[str, int, str] | None:
    direct = _decode_ascii_handle_at(data, base_address, anchor_rel)
    if direct is not None:
        return direct
    direct = _decode_triplet_at(data, base_address, anchor_rel)
    if direct is not None:
        return direct

    start = max(0, anchor_rel - slack)
    end = min(len(data), anchor_rel + slack + 16)
    window = data[start:end]
    window_base = base_address + start

    best: tuple[str, int, str, int] | None = None
    for rel_offset, handle, _encoding in extract_handle_hits(window):
        dist = abs((window_base + rel_offset) - (base_address + anchor_rel))
        if best is None or dist < best[3]:
            best = (handle, window_base + rel_offset, StringEncoding.ASCII_Z.value, dist)
    for triplet in extract_profile_triplets(window, base_offset=window_base):
        dist = abs(triplet.offset - (base_address + anchor_rel))
        if best is None or dist < best[3]:
            best = (
                handle_from_triplet(triplet),
                triplet.offset,
                "profile_triplet",
                dist,
            )
    if best is None:
        return None
    return best[0], best[1], best[2]


def _try_pointer_indirect(
    process_handle,
    anchor_address: int,
) -> tuple[str, int, str] | None:
    raw = _read_memory(process_handle, anchor_address, 8)
    if not raw or len(raw) < 8:
        return None
    pointer = struct.unpack_from("<Q", raw, 0)[0]
    if pointer < 0x10000 or pointer > 0x7FFFFFFFFFFF:
        return None
    target = _read_memory(process_handle, pointer, 128)
    if not target:
        return None
    for rel_offset, handle, _encoding in extract_handle_hits(target):
        return handle, pointer + rel_offset, "ascii_z_indirect"
    for triplet in extract_profile_triplets(target, base_offset=pointer):
        return handle_from_triplet(triplet), triplet.offset, "profile_triplet_indirect"
    return None


def read_host_handle_anchor(
    process_handle,
    modules,
    *,
    offset: int | str = DEFAULT_HOST_HANDLE_MODULE_OFFSET,
    module_names: tuple[str, ...] = DEFAULT_SC2_MODULE_NAMES,
    window_bytes: int = DEFAULT_HOST_ANCHOR_WINDOW,
) -> HostHandleAnchor | None:
    """Read the host handle stored at ``module_base + offset``."""
    module = _find_sc2_module(modules, module_names)
    if module is None:
        return None

    anchor_offset = parse_module_offset(offset)
    if anchor_offset < 0 or anchor_offset >= module.size:
        return None

    anchor_address = module.base + anchor_offset
    read_start = max(module.base, anchor_address - 64)
    read_end = min(module.base + module.size, anchor_address + window_bytes)
    data = _read_memory(process_handle, read_start, read_end - read_start)
    if not data:
        return None

    anchor_rel = anchor_address - read_start
    decoded = _decode_handle_near(data, read_start, anchor_rel)
    if decoded is None:
        decoded = _try_pointer_indirect(process_handle, anchor_address)
    if decoded is None:
        return None

    handle, handle_address, encoding = decoded
    module_label = f"{module.name}+0x{anchor_offset:X}"
    return HostHandleAnchor(
        module_name=module.name,
        module_base=module.base,
        anchor_offset=anchor_offset,
        anchor_address=anchor_address,
        handle=handle,
        handle_address=handle_address,
        encoding=encoding,
        module_label=module_label,
    )


def read_host_handle_from_process(
    process_handle,
    *,
    pid: int,
    offset: int | str = DEFAULT_HOST_HANDLE_MODULE_OFFSET,
    module_names: tuple[str, ...] = DEFAULT_SC2_MODULE_NAMES,
) -> HostHandleAnchor | None:
    from antismurf.lobby.memory_probe import build_module_map

    modules = build_module_map(pid)
    return read_host_handle_anchor(
        process_handle,
        modules,
        offset=offset,
        module_names=module_names,
    )


def scan_module_vicinity_handles(
    process_handle,
    anchor: HostHandleAnchor,
    modules,
    *,
    radius: int = DEFAULT_HOST_ANCHOR_VICINITY_RADIUS,
) -> list[VicinityHandleHit]:
    """Collect handles in the SC2 module image near the host anchor."""
    module = _find_sc2_module(modules, (anchor.module_name,))
    if module is None:
        module = type("Mod", (), {"base": anchor.module_base, "size": radius * 2})()

    span_start = max(module.base, anchor.anchor_address - radius)
    span_end = min(module.base + module.size, anchor.anchor_address + radius)
    if span_end <= span_start:
        return []

    data = _read_memory(process_handle, span_start, span_end - span_start)
    if not data:
        return []

    by_handle: dict[str, VicinityHandleHit] = {}
    for rel_offset, handle, encoding in extract_handle_hits(data):
        address = span_start + rel_offset
        hit = VicinityHandleHit(
            address=address,
            handle=handle,
            encoding=encoding.value if hasattr(encoding, "value") else str(encoding),
            offset_from_anchor=address - anchor.anchor_address,
        )
        existing = by_handle.get(handle)
        if existing is None or abs(hit.offset_from_anchor) < abs(existing.offset_from_anchor):
            by_handle[handle] = hit

    for triplet in extract_profile_triplets(data, base_offset=span_start):
        handle = handle_from_triplet(triplet)
        hit = VicinityHandleHit(
            address=triplet.offset,
            handle=handle,
            encoding="profile_triplet",
            offset_from_anchor=triplet.offset - anchor.anchor_address,
        )
        existing = by_handle.get(handle)
        if existing is None or abs(hit.offset_from_anchor) < abs(existing.offset_from_anchor):
            by_handle[handle] = hit

    return sorted(
        by_handle.values(),
        key=lambda item: (abs(item.offset_from_anchor), item.address),
    )


def anchor_proximity_bonus(
    address: int,
    anchor: HostHandleAnchor,
    *,
    radius: int = DEFAULT_HOST_ANCHOR_VICINITY_RADIUS,
) -> tuple[float, list[str]]:
    distance = abs(address - anchor.anchor_address)
    if address == anchor.handle_address:
        return 80.0, ["host anchor handle (+80)"]
    if distance == 0:
        return 75.0, ["host anchor slot (+75)"]
    if distance <= 256:
        return 60.0, [f"host anchor ±256B (+60, Δ{distance})"]
    if distance <= 4096:
        return 35.0, [f"host module table (+35, Δ{distance})"]
    if distance <= radius:
        return 15.0, [f"host anchor vicinity (+15, Δ{distance})"]
    return 0.0, []


def detect_host_handle(
    process_handle,
    *,
    pid: int,
    offset: int | str = DEFAULT_HOST_HANDLE_MODULE_OFFSET,
) -> str | None:
    anchor = read_host_handle_from_process(
        process_handle,
        pid=pid,
        offset=offset,
    )
    return anchor.handle if anchor else None
