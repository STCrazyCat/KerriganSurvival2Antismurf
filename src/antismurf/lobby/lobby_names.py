from __future__ import annotations

import re
from dataclasses import dataclass

from antismurf.config.settings import AppConfig
from antismurf.lobby.lobby_handles import HandleHit
from antismurf.lobby.memory_formats import (
    StringEncoding,
    scan_sc2_byte_strings,
    scan_utf16le_null_strings,
)
from antismurf.lobby.memory_profile_store import MemoryProfileStore, NameOffsetHint
from antismurf.lobby.memory_reader import _read_memory
from antismurf.vision.lobby_text_parser import parse_lobby_identity

_SKIP_NAMES = frozenset(
    {
        "",
        "computer",
        "neutral",
        "ai",
        "open",
        "closed",
        "starcraft",
        "battle.net",
    }
)


@dataclass(frozen=True)
class NameMatch:
    display_name: str
    name_encoding: str
    name_address: int
    offset_from_handle: int


def is_memory_display_name(text: str) -> bool:
    text = text.strip()
    if len(text) < 2 or len(text) > 32:
        return False
    if "-S2-" in text:
        return False
    if text.lower() in _SKIP_NAMES:
        return False
    if parse_lobby_identity(text) is not None:
        return True
    if re.search(r"[\u4e00-\u9fffA-Za-z]", text):
        return True
    return False


def _decoded_to_match(
    decoded,
    *,
    handle_address: int,
    window_base: int,
) -> NameMatch | None:
    if not is_memory_display_name(decoded.text):
        return None
    name_address = window_base + decoded.offset
    return NameMatch(
        display_name=decoded.text,
        name_encoding=decoded.encoding.value,
        name_address=name_address,
        offset_from_handle=name_address - handle_address,
    )


def _scan_window_for_names(
    data: bytes,
    *,
    handle_address: int,
    window_base: int,
) -> list[NameMatch]:
    matches: list[NameMatch] = []
    for decoded in scan_utf16le_null_strings(data):
        match = _decoded_to_match(
            decoded,
            handle_address=handle_address,
            window_base=window_base,
        )
        if match:
            matches.append(match)
    for decoded in scan_sc2_byte_strings(data):
        match = _decoded_to_match(
            decoded,
            handle_address=handle_address,
            window_base=window_base,
        )
        if match:
            matches.append(match)
    return matches


def _try_offset_hint(
    process_handle,
    handle_address: int,
    hint: NameOffsetHint,
    config: AppConfig,
) -> NameMatch | None:
    name_address = handle_address + hint.offset_from_handle
    read_size = 128
    data = _read_memory(
        process_handle,
        max(0, name_address - 8),
        read_size,
    )
    if not data:
        return None
    window_base = max(0, name_address - 8)
    if hint.name_encoding == StringEncoding.UTF16_LE_Z.value:
        for decoded in scan_utf16le_null_strings(data):
            match = _decoded_to_match(
                decoded,
                handle_address=handle_address,
                window_base=window_base,
            )
            if match:
                return match
    elif hint.name_encoding == StringEncoding.SC2_BYTE_STRING.value:
        for decoded in scan_sc2_byte_strings(data):
            match = _decoded_to_match(
                decoded,
                handle_address=handle_address,
                window_base=window_base,
            )
            if match:
                return match
    return None


def find_display_name_near(
    process_handle,
    address: int,
    config: AppConfig,
    *,
    offset_hints: list[NameOffsetHint] | None = None,
) -> NameMatch | None:
    if offset_hints:
        for hint in offset_hints:
            match = _try_offset_hint(process_handle, address, hint, config)
            if match:
                return match

    radius = config.memory_name_search_radius
    window_base = max(0, address - radius)
    data = _read_memory(process_handle, window_base, radius * 2)
    if not data:
        return None

    candidates = _scan_window_for_names(
        data,
        handle_address=address,
        window_base=window_base,
    )
    if not candidates:
        return None
    candidates.sort(
        key=lambda item: (abs(item.offset_from_handle), -len(item.display_name))
    )
    return candidates[0]


def attach_display_names(
    process_handle,
    hits: list[HandleHit],
    handles: list[str],
    config: AppConfig,
    *,
    store: MemoryProfileStore | None = None,
    session_id: int | None = None,
) -> dict[str, str]:
    profile_store = store or MemoryProfileStore()
    offset_hints = (
        profile_store.common_name_offsets() if config.memory_targeted_scan_enabled else []
    )
    by_handle: dict[str, str] = {}
    hits_by_handle: dict[str, list[HandleHit]] = {}
    for hit in hits:
        hits_by_handle.setdefault(hit.handle, []).append(hit)

    for handle in handles:
        for hit in hits_by_handle.get(handle, []):
            match = find_display_name_near(
                process_handle,
                hit.address,
                config,
                offset_hints=offset_hints,
            )
            if not match:
                continue
            by_handle[handle] = match.display_name
            if session_id is not None and config.memory_record_enabled:
                profile_store.record_name_binding(
                    session_id,
                    handle=handle,
                    display_name=match.display_name,
                    name_encoding=match.name_encoding,
                    handle_address=hit.address,
                    name_address=match.name_address,
                )
            break
    return by_handle
