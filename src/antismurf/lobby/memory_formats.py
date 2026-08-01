"""StarCraft II in-process string layouts (handles, names, profile ids).

References:
- Replay lobby ``m_toonHandle`` / ``m_name`` in initData (ASCII handle + separate name)
  https://github.com/Blizzard/s2protocol/blob/master/docs/flags/initdata.md
- Replay serialized byte strings (length-prefixed, sign bit on length)
  https://github.com/GraylinKim/sc2reader/wiki/Serialized-Data
- Windows client UI strings are typically UTF-16 LE (WCHAR, null-terminated)

Handles (``5-S2-1-1234567``) are **always ASCII** in Blizzard data; do not UTF-16-decode
handle search windows or matches will be missed / corrupted.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from enum import Enum

from antismurf.models.player import (
    HANDLE_ASCII_BYTES,
    extract_handle_from_text,
    is_valid_handle,
    parse_handle_parts,
)

# SC2 replay serialized string type tags (sc2reader wiki)
SC2_SERIALIZED_BYTE_STRING = 0x0A
SC2_SERIALIZED_UTF8_STRING = 0x09


class StringEncoding(str, Enum):
    ASCII_Z = "ascii_z"
    UTF16_LE_Z = "utf16_le_z"
    SC2_BYTE_STRING = "sc2_byte_string"
    UTF8_Z = "utf8_z"


@dataclass(frozen=True)
class DecodedString:
    text: str
    encoding: StringEncoding
    offset: int
    length: int


@dataclass(frozen=True)
class ProfileTriplet:
    region_id: int
    realm_id: int
    profile_id: int
    offset: int


def scan_ascii_null_strings(
    data: bytes,
    *,
    min_len: int = 2,
    max_len: int = 64,
) -> list[DecodedString]:
    results: list[DecodedString] = []
    start = 0
    while start < len(data):
        end = data.find(b"\x00", start)
        if end < 0:
            break
        if end > start:
            length = end - start
            if min_len <= length <= max_len:
                try:
                    text = data[start:end].decode("ascii")
                except UnicodeDecodeError:
                    start = end + 1
                    continue
                if text.isprintable() or re.search(r"[\u4e00-\u9fff]", text):
                    results.append(
                        DecodedString(text, StringEncoding.ASCII_Z, start, length)
                    )
        start = end + 1
    return results


def scan_utf16le_null_strings(
    data: bytes,
    *,
    min_chars: int = 2,
    max_chars: int = 32,
) -> list[DecodedString]:
    results: list[DecodedString] = []
    i = 0
    while i < len(data) - 3:
        if i > 0 and not (data[i - 2] == 0 and data[i - 1] == 0):
            i += 2
            continue
        chars: list[str] = []
        j = i
        while j < len(data) - 1:
            code = int.from_bytes(data[j : j + 2], "little")
            if code == 0:
                break
            if code < 32 or code > 0x10FFFF:
                break
            try:
                chars.append(chr(code))
            except ValueError:
                break
            j += 2
            if len(chars) > max_chars:
                break
        if min_chars <= len(chars) <= max_chars:
            text = "".join(chars).strip()
            if text:
                results.append(
                    DecodedString(
                        text,
                        StringEncoding.UTF16_LE_Z,
                        i,
                        j - i,
                    )
                )
        i = j + 2 if j > i else i + 2
    return results


def scan_sc2_byte_strings(data: bytes) -> list[DecodedString]:
    """Parse SC2 replay-style length-prefixed byte strings in a memory window."""
    results: list[DecodedString] = []
    i = 0
    while i < len(data) - 2:
        tag = data[i]
        if tag not in (SC2_SERIALIZED_BYTE_STRING, SC2_SERIALIZED_UTF8_STRING):
            i += 1
            continue
        raw_len = data[i + 1]
        length = raw_len >> 1
        if length <= 0 or i + 2 + length > len(data):
            i += 1
            continue
        payload = data[i + 2 : i + 2 + length]
        encoding = (
            StringEncoding.UTF8_Z
            if tag == SC2_SERIALIZED_UTF8_STRING
            else StringEncoding.SC2_BYTE_STRING
        )
        try:
            text = payload.decode("utf-8" if tag == SC2_SERIALIZED_UTF8_STRING else "latin-1")
        except UnicodeDecodeError:
            i += 1
            continue
        text = text.strip("\x00")
        if 2 <= len(text) <= 32:
            results.append(DecodedString(text, encoding, i, 2 + length))
        i += 2 + length
    return results


def extract_handle_hits(data: bytes, base_offset: int = 0) -> list[tuple[int, str, StringEncoding]]:
    """Find Battle.net handles — ASCII only (``m_toonHandle`` format)."""
    hits: list[tuple[int, str, StringEncoding]] = []
    for match in HANDLE_ASCII_BYTES.finditer(data):
        handle = match.group(0).decode("ascii", errors="ignore")
        if is_valid_handle(handle):
            hits.append(
                (base_offset + match.start(), handle, StringEncoding.ASCII_Z)
            )
    return hits


def extract_profile_triplets(
    data: bytes,
    base_offset: int = 0,
    *,
    program_id: int = 2,
) -> list[ProfileTriplet]:
    """Scan for little-endian (region, program=S2, realm, profile_id) uint32 blocks."""
    results: list[ProfileTriplet] = []
    if len(data) < 16:
        return results
    for offset in range(0, len(data) - 15, 4):
        region, prog, realm, profile = struct.unpack_from("<4I", data, offset)
        if prog != program_id:
            continue
        if region < 1 or region > 9:
            continue
        if realm < 1 or realm > 2:
            continue
        if profile < 1 or profile > 50_000_000:
            continue
        handle = f"{region}-S2-{realm}-{profile}"
        if is_valid_handle(handle):
            results.append(
                ProfileTriplet(region, realm, profile, base_offset + offset)
            )
    return results


def handle_from_triplet(triplet: ProfileTriplet) -> str:
    return f"{triplet.region_id}-S2-{triplet.realm_id}-{triplet.profile_id}"


def triplet_matches_handle(triplet: ProfileTriplet, handle: str) -> bool:
    parts = parse_handle_parts(handle)
    if parts is None:
        return False
    return (
        parts.server_id == triplet.region_id
        and parts.realm_id == triplet.realm_id
        and parts.player_id == triplet.profile_id
    )
