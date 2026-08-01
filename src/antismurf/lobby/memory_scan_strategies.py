"""Multi-encoding scan strategies for SC2 lobby memory probe."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from antismurf.lobby.memory_formats import (
    extract_handle_hits,
    extract_profile_triplets,
    scan_ascii_null_strings,
    scan_sc2_byte_strings,
    scan_utf16le_null_strings,
)
from antismurf.lobby.memory_reader import _read_memory
from antismurf.models.player import is_valid_handle, parse_handle_parts


@dataclass
class ScanStrategies:
    """Toggle which memory decodings / handle layouts to try."""

    name_utf16_le: bool = True
    name_utf8: bool = True
    name_ascii: bool = True
    name_sc2_byte: bool = True
    handle_ascii_exact: bool = True
    handle_ascii_regex: bool = True
    handle_utf16_le: bool = True
    handle_profile_triplet: bool = True
    require_exact_handle_bytes: bool = True
    prefer_private_heap: bool = True
    raw_byte_match: bool = True
    prefer_heap_first: bool = True
    allow_remote_pairing: bool = True
    max_image_hits: int = 8
    use_channel_roster: bool = True
    channel_roster_min_members: int = 2
    channel_roster_max_span: int = 8192
    use_lobby_member_struct: bool = True
    lobby_member_record_size: int = 0x1B8
    lobby_member_max_slots: int = 12
    use_host_anchor: bool = True
    host_handle_module_offset: int = 0x3E2F340
    host_anchor_scan_radius: int = 8192


DEFAULT_SCAN_STRATEGIES = ScanStrategies()


@dataclass(frozen=True)
class DecodedStringHit:
    address: int
    text: str
    encoding: str
    strategy: str


@dataclass(frozen=True)
class DecodedHandleHit:
    address: int
    handle: str
    encoding: str
    strategy: str
    exact: bool = False


@dataclass
class ComprehensiveScanStats:
    name_hits: dict[str, int] = field(default_factory=dict)
    handle_hits: dict[str, int] = field(default_factory=dict)
    pair_attempts: int = 0

    def note_name(self, strategy: str) -> None:
        self.name_hits[strategy] = self.name_hits.get(strategy, 0) + 1

    def note_handle(self, strategy: str) -> None:
        self.handle_hits[strategy] = self.handle_hits.get(strategy, 0) + 1


def _inc(stats: ComprehensiveScanStats | None, bucket: str, key: str) -> None:
    if stats is None:
        return
    if bucket == "name":
        stats.note_name(key)
    else:
        stats.note_handle(key)


def read_null_string_at(
    process_handle,
    address: int,
    *,
    encoding: str,
    max_bytes: int = 128,
) -> str | None:
    data = _read_memory(process_handle, address, max_bytes)
    if not data:
        return None
    if encoding == "utf16_le_z":
        chars: list[str] = []
        for index in range(0, len(data) - 1, 2):
            code = int.from_bytes(data[index : index + 2], "little")
            if code == 0:
                break
            if code < 32:
                return None
            chars.append(chr(code))
        text = "".join(chars)
        return text or None
    if encoding in {"ascii_z", "utf8_z"}:
        end = data.find(b"\x00")
        if end <= 0:
            return None
        try:
            return data[:end].decode("utf-8" if encoding == "utf8_z" else "ascii")
        except UnicodeDecodeError:
            return None
    return None


def verify_name_bytes_at(
    process_handle,
    address: int,
    display_name: str,
    *,
    encoding: str,
) -> bool:
    """CE-style: accept exact byte match at address."""
    if encoding == "utf16_le_z":
        needle = display_name.encode("utf-16-le")
    elif encoding == "utf8_z":
        needle = display_name.encode("utf-8")
    elif encoding == "ascii_z":
        if not display_name.isascii():
            return False
        needle = display_name.encode("ascii")
    else:
        return False
    data = _read_memory(process_handle, address, len(needle) + 4)
    if not data or len(data) < len(needle):
        return False
    return data[: len(needle)] == needle


def verify_handle_bytes_at(
    process_handle,
    address: int,
    expected_handle: str,
    *,
    encoding: str = "ascii_z",
) -> bool:
    """CE-style: accept exact handle bytes at address."""
    if encoding == "ascii_z":
        needle = expected_handle.encode("ascii")
    elif encoding == "utf16_le_z":
        needle = expected_handle.encode("utf-16-le")
    else:
        return False
    data = _read_memory(process_handle, address, len(needle) + 4)
    if not data or len(data) < len(needle):
        return False
    if data[: len(needle)] != needle:
        return False
    return is_valid_handle(expected_handle)


def _accept_string_hit(
    process_handle,
    address: int,
    display_name: str,
    *,
    encoding: str,
    strategy: str,
    strategies: ScanStrategies,
    seen: set[tuple[int, str]],
    hits: list[DecodedStringHit],
    stats: ComprehensiveScanStats | None,
) -> None:
    if strategies.raw_byte_match and verify_name_bytes_at(
        process_handle,
        address,
        display_name,
        encoding=encoding,
    ):
        key = (address, f"{strategy}_raw")
        if key not in seen:
            seen.add(key)
            hits.append(
                DecodedStringHit(
                    address=address,
                    text=display_name,
                    encoding=encoding,
                    strategy=f"{strategy}_raw",
                )
            )
            _inc(stats, "name", f"{strategy}_raw")
        return

    decoded = read_null_string_at(process_handle, address, encoding=encoding)
    if decoded is None or decoded.strip() != display_name.strip():
        return
    key = (address, strategy)
    if key in seen:
        return
    seen.add(key)
    hits.append(
        DecodedStringHit(
            address=address,
            text=decoded,
            encoding=encoding,
            strategy=strategy,
        )
    )
    _inc(stats, "name", strategy)


def _accept_handle_hit(
    process_handle,
    address: int,
    expected_handle: str,
    *,
    encoding: str,
    strategy: str,
    strategies: ScanStrategies,
    seen: set[tuple[int, str]],
    hits: list[DecodedHandleHit],
    stats: ComprehensiveScanStats | None,
) -> None:
    if strategies.raw_byte_match and verify_handle_bytes_at(
        process_handle,
        address,
        expected_handle,
        encoding=encoding,
    ):
        key = (address, f"{strategy}_raw")
        if key not in seen:
            seen.add(key)
            hits.append(
                DecodedHandleHit(
                    address=address,
                    handle=expected_handle,
                    encoding=encoding,
                    strategy=f"{strategy}_raw",
                    exact=True,
                )
            )
            _inc(stats, "handle", f"{strategy}_raw")
        return

    decoded = read_null_string_at(
        process_handle,
        address,
        encoding=encoding,
        max_bytes=64,
    )
    if decoded is None:
        if encoding == "ascii_z" and strategy.endswith("_z"):
            decoded = expected_handle
        else:
            return
    if not is_valid_handle(decoded):
        return
    if strategies.require_exact_handle_bytes and decoded != expected_handle:
        return
    key = (address, strategy)
    if key in seen:
        return
    seen.add(key)
    hits.append(
        DecodedHandleHit(
            address=address,
            handle=decoded,
            encoding=encoding,
            strategy=strategy,
            exact=True,
        )
    )
    _inc(stats, "handle", strategy)


def scan_process_for_decoded_strings(
    process_handle,
    display_name: str,
    scan_bytes_fn,
    *,
    strategies: ScanStrategies = DEFAULT_SCAN_STRATEGIES,
    time_budget_sec: float = 30.0,
    max_hits: int = 80,
    stats: ComprehensiveScanStats | None = None,
) -> list[DecodedStringHit]:
    """Find nickname using multiple encodings (substring search + on-site decode verify)."""
    hits: list[DecodedStringHit] = []
    seen: set[tuple[int, str]] = set()

    needles: list[tuple[str, str, bytes]] = []
    if strategies.name_utf16_le:
        needles.append(("utf16_le_z", "name_utf16_le", display_name.encode("utf-16-le")))
    if strategies.name_utf8:
        needles.append(("utf8_z", "name_utf8", display_name.encode("utf-8")))
    if strategies.name_ascii and display_name.isascii():
        needles.append(("ascii_z", "name_ascii", display_name.encode("ascii")))

    per_needle_budget = time_budget_sec / max(len(needles), 1)
    for encoding, strategy, needle in needles:
        for address in scan_bytes_fn(
            process_handle,
            needle,
            time_budget_sec=per_needle_budget,
            max_hits=max_hits,
        ):
            _accept_string_hit(
                process_handle,
                address,
                display_name,
                encoding=encoding,
                strategy=strategy,
                strategies=strategies,
                seen=seen,
                hits=hits,
                stats=stats,
            )
    return hits


def scan_process_for_decoded_handles(
    process_handle,
    expected_handle: str,
    scan_bytes_fn,
    *,
    strategies: ScanStrategies = DEFAULT_SCAN_STRATEGIES,
    time_budget_sec: float = 30.0,
    max_hits: int = 80,
    stats: ComprehensiveScanStats | None = None,
) -> list[DecodedHandleHit]:
    hits: list[DecodedHandleHit] = []
    seen: set[tuple[int, str]] = set()

    needles: list[tuple[str, str, bytes]] = []
    if strategies.handle_ascii_exact:
        needles.append(("ascii_z", "handle_ascii_exact", expected_handle.encode("ascii")))
        needles.append(
            ("ascii_z", "handle_ascii_exact_z", expected_handle.encode("ascii") + b"\x00")
        )
    if strategies.handle_utf16_le:
        needles.append(
            ("utf16_le_z", "handle_utf16_le", expected_handle.encode("utf-16-le"))
        )

    per_needle_budget = time_budget_sec / max(len(needles), 1)
    for encoding, strategy, needle in needles:
        for address in scan_bytes_fn(
            process_handle,
            needle,
            time_budget_sec=per_needle_budget,
            max_hits=max_hits,
        ):
            _accept_handle_hit(
                process_handle,
                address,
                expected_handle,
                encoding=encoding,
                strategy=strategy,
                strategies=strategies,
                seen=seen,
                hits=hits,
                stats=stats,
            )

    return hits


def collect_handles_in_window(
    data: bytes,
    *,
    window_base: int,
    anchor_address: int,
    expected_handle: str,
    strategies: ScanStrategies = DEFAULT_SCAN_STRATEGIES,
    stats: ComprehensiveScanStats | None = None,
) -> list[DecodedHandleHit]:
    found: list[DecodedHandleHit] = []
    seen: set[tuple[int, str, str]] = set()

    if strategies.handle_ascii_regex:
        for rel_offset, handle, _enc in extract_handle_hits(data):
            address = window_base + rel_offset
            key = (address, handle, "handle_ascii_regex")
            if key in seen:
                continue
            seen.add(key)
            exact = handle == expected_handle
            if strategies.require_exact_handle_bytes and not exact:
                continue
            found.append(
                DecodedHandleHit(
                    address=address,
                    handle=handle,
                    encoding="ascii_z",
                    strategy="handle_ascii_regex",
                    exact=exact,
                )
            )
            _inc(stats, "handle", "handle_ascii_regex")

    if strategies.handle_ascii_exact:
        needle = expected_handle.encode("ascii")
        pos = 0
        while True:
            rel = data.find(needle, pos)
            if rel < 0:
                break
            address = window_base + rel
            key = (address, expected_handle, "handle_ascii_exact_window")
            if key not in seen:
                seen.add(key)
                found.append(
                    DecodedHandleHit(
                        address=address,
                        handle=expected_handle,
                        encoding="ascii_z",
                        strategy="handle_ascii_exact_window",
                        exact=True,
                    )
                )
                _inc(stats, "handle", "handle_ascii_exact_window")
            pos = rel + 1

    if strategies.handle_utf16_le:
        wide = expected_handle.encode("utf-16-le")
        pos = 0
        while True:
            rel = data.find(wide, pos)
            if rel < 0:
                break
            address = window_base + rel
            key = (address, expected_handle, "handle_utf16_le_window")
            if key not in seen:
                seen.add(key)
                found.append(
                    DecodedHandleHit(
                        address=address,
                        handle=expected_handle,
                        encoding="utf16_le_z",
                        strategy="handle_utf16_le_window",
                        exact=True,
                    )
                )
                _inc(stats, "handle", "handle_utf16_le_window")
            pos = rel + 2

    if strategies.handle_profile_triplet:
        parts = parse_handle_parts(expected_handle)
        if parts is not None:
            for triplet in extract_profile_triplets(data, base_offset=0):
                if (
                    triplet.region_id == parts.server_id
                    and triplet.realm_id == parts.realm_id
                    and triplet.profile_id == parts.player_id
                ):
                    address = window_base + triplet.offset
                    key = (address, expected_handle, "handle_profile_triplet")
                    if key in seen:
                        continue
                    seen.add(key)
                    found.append(
                        DecodedHandleHit(
                            address=address,
                            handle=expected_handle,
                            encoding="profile_triplet",
                            strategy="handle_profile_triplet",
                            exact=True,
                        )
                    )
                    _inc(stats, "handle", "handle_profile_triplet")

    found.sort(key=lambda item: abs(item.address - anchor_address))
    return found


def collect_names_in_window(
    data: bytes,
    *,
    window_base: int,
    anchor_address: int,
    expected_name: str,
    strategies: ScanStrategies = DEFAULT_SCAN_STRATEGIES,
    stats: ComprehensiveScanStats | None = None,
) -> list[DecodedStringHit]:
    found: list[DecodedStringHit] = []
    seen: set[tuple[int, str]] = set()

    if strategies.name_utf16_le:
        for decoded in scan_utf16le_null_strings(data):
            if decoded.text.strip() != expected_name.strip():
                continue
            address = window_base + decoded.offset
            key = (address, "name_utf16_le_window")
            if key in seen:
                continue
            seen.add(key)
            found.append(
                DecodedStringHit(
                    address=address,
                    text=decoded.text,
                    encoding="utf16_le_z",
                    strategy="name_utf16_le_window",
                )
            )
            _inc(stats, "name", "name_utf16_le_window")

    if strategies.name_utf8:
        for decoded in scan_ascii_null_strings(data):
            if decoded.text.strip() != expected_name.strip():
                continue
            address = window_base + decoded.offset
            key = (address, "name_utf8_window")
            if key in seen:
                continue
            seen.add(key)
            found.append(
                DecodedStringHit(
                    address=address,
                    text=decoded.text,
                    encoding="utf8_z",
                    strategy="name_utf8_window",
                )
            )
            _inc(stats, "name", "name_utf8_window")

    if strategies.name_sc2_byte:
        for decoded in scan_sc2_byte_strings(data):
            if decoded.text.strip() != expected_name.strip():
                continue
            address = window_base + decoded.offset
            key = (address, "name_sc2_byte_window")
            if key in seen:
                continue
            seen.add(key)
            found.append(
                DecodedStringHit(
                    address=address,
                    text=decoded.text,
                    encoding=decoded.encoding.value,
                    strategy="name_sc2_byte_window",
                )
            )
            _inc(stats, "name", "name_sc2_byte_window")

    found.sort(key=lambda item: abs(item.address - anchor_address))
    return found
