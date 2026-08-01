"""SC2 game-lobby channel roster as fixed-size member structs (CE layout).

Discovered layout (stride ``0x1B8`` / 440 bytes per player):

  +0x00  uint64   heap pointer (optional display sub-object; often non-zero)
  +0x08  uint64   internal id / session key
  +0x10  uint32   region (e.g. 5)
  +0x14  uint32   program tag ``"2S"`` → ``0x00005332`` (not uint32 ``2``)
  +0x18  uint32   realm (1–2)
  +0x1C  uint32   reserved / padding
  +0x20  uint32   profile_id  ← Battle.net handle numeric part
  +0x24..+0x47     optional team tag / padding
  +0x48..+0x7F     utf8_z lobby label (``<战队>昵称#tag``; often starts at +0x48)

The roster array is **not** always anchored at slot 0. When the local host joins
another player's room, their struct may sit at index N>0; slots ``0..N-1`` live at
``record_base - k*0x1B8``. Always scan backward from the host/anchor record.

Multiple consecutive records form the in-room player list.
"""

from __future__ import annotations

import re
import struct
import time
from dataclasses import dataclass

from antismurf.lobby.memory_channel_roster import ChannelRosterCluster, _dedupe_clusters
from antismurf.lobby.memory_reader import _iter_readable_regions_typed, _read_memory
from antismurf.models.player import is_valid_handle, parse_handle_parts

LOBBY_MEMBER_RECORD_SIZE = 0x1B8
LOBBY_PROGRAM_S2_TAG = 0x00005332  # bytes 32 53 00 00 ("2S")
OFF_MEMBER_PTR = 0x00
OFF_MEMBER_INTERNAL_ID = 0x08
OFF_MEMBER_REGION = 0x10
OFF_MEMBER_PROGRAM = 0x14
OFF_MEMBER_REALM = 0x18
OFF_MEMBER_PROFILE_ID = 0x20
OFF_MEMBER_NAME_UTF8 = 0x54
NAME_UTF8_OFFSET_CANDIDATES = (0x48, 0x4C, 0x50, 0x54, 0x58, 0x5C)
TEAM_UTF8_OFFSET_CANDIDATES = (0x28, 0x2C, 0x30, 0x34, 0x38, 0x3C, 0x40, 0x44, 0x48)
MIN_PROFILE_ID = 1
MAX_PROFILE_ID = 50_000_000
MAX_ROSTER_BACKWARD_SLOTS = 11
LOBBY_UI_SLOT_COUNT = 10

_ROSTER_TEAM_NICK_RE = re.compile(r"^<#?([^<>]{1,48})>(.+)$", re.DOTALL)
_TEAM_ONLY_RE = re.compile(r"^<#?([^<>]{1,48})>$")
_DISPLAY_TAG_SUFFIX_RE = re.compile(r"#(\d{1,5})$")

@dataclass(frozen=True)
class LobbyMemberRecord:
    record_base: int
    profile_address: int
    handle: str
    region_id: int
    realm_id: int
    profile_id: int
    display_name: str | None = None
    team_name: str | None = None
    raw_display_name: str | None = None
    internal_id: int | None = None

    def summary_line(self) -> str:
        name = self.display_name or "?"
        team = f"<{self.team_name}> " if self.team_name else ""
        return (
            f"  @{self.record_base:#x} profile@{self.profile_address:#x} "
            f"{self.handle} {team}\"{name}\""
        )


def _clean_nickname(nickname: str) -> str:
    text = nickname.strip()
    if not text:
        return ""
    return _DISPLAY_TAG_SUFFIX_RE.sub("", text).strip()


def parse_roster_display_name(raw: str | None) -> tuple[str | None, str]:
    """Split lobby label into optional team prefix and nickname."""
    text = (raw or "").strip()
    if not text:
        return None, ""
    team_only = _TEAM_ONLY_RE.match(text)
    if team_only:
        team = team_only.group(1).strip() or None
        return team, ""
    match = _ROSTER_TEAM_NICK_RE.match(text)
    if match:
        team = match.group(1).strip() or None
        nickname = _clean_nickname(match.group(2))
        return team, nickname
    return None, _clean_nickname(text)


def _decode_utf8_z_candidates(
    data: bytes,
    rel_base: int,
    offsets: tuple[int, ...],
    *,
    max_len: int = 96,
) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    seen: set[str] = set()
    for offset in offsets:
        text = _decode_utf8_z(data, rel_base + offset, max_len=max_len)
        if not text or text in seen:
            continue
        seen.add(text)
        found.append((offset, text))
    return found


def _pick_best_label_text(candidates: list[tuple[int, str]]) -> str | None:
    if not candidates:
        return None

    def score(item: tuple[int, str]) -> tuple[int, int, int]:
        offset, text = item
        cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
        # Prefer earlier offsets (0x48) when length ties; longer text wins overall.
        return (len(text), cjk, -offset)

    _offset, best = max(candidates, key=score)
    return best


def _find_team_tag(data: bytes, rel_base: int) -> str | None:
    for offset, text in _decode_utf8_z_candidates(
        data,
        rel_base,
        TEAM_UTF8_OFFSET_CANDIDATES,
        max_len=48,
    ):
        if _TEAM_ONLY_RE.match(text):
            team, _ = parse_roster_display_name(text)
            if team:
                return team
        team, nick = parse_roster_display_name(text)
        if team and not nick:
            return team
    return None


def _read_member_display_raw(data: bytes, rel_base: int) -> str | None:
    candidates = _decode_utf8_z_candidates(
        data,
        rel_base,
        NAME_UTF8_OFFSET_CANDIDATES,
    )
    return _pick_best_label_text(candidates)


def describe_lobby_member_record(data: bytes, *, record_base: int) -> list[str]:
    """Human-readable summary of known fields in one 440-byte record."""
    lines = [f"record @ {record_base:#x} ({LOBBY_MEMBER_RECORD_SIZE} bytes)"]
    if len(data) < OFF_MEMBER_NAME_UTF8 + 1:
        lines.append("  (truncated)")
        return lines
    if len(data) >= OFF_MEMBER_PTR + 8:
        ptr = struct.unpack_from("<Q", data, OFF_MEMBER_PTR)[0]
        lines.append(f"  +0x00 ptr/sub-object = {ptr:#x}")
    if len(data) >= OFF_MEMBER_INTERNAL_ID + 8:
        internal = struct.unpack_from("<Q", data, OFF_MEMBER_INTERNAL_ID)[0]
        lines.append(f"  +0x08 internal_id = {internal:#x}")
    identity = _record_identity_valid(data, 0)
    if identity:
        region, realm, profile_id, handle = identity
        lines.append(
            f"  +0x10 identity region={region} program=2S realm={realm} "
            f"profile_id={profile_id} handle={handle}"
        )
    raw_name = _read_member_display_raw(data, rel_base)
    if raw_name:
        team, nick = parse_roster_display_name(raw_name)
        lines.append(f"  name utf8 raw = {raw_name!r}")
        if team:
            lines.append(f"       team = {team!r} nickname = {nick!r}")
    return lines

def handle_from_identity(region: int, realm: int, profile_id: int) -> str | None:
    handle = f"{region}-S2-{realm}-{profile_id}"
    if is_valid_handle(handle):
        return handle
    return None


def _decode_utf8_z(data: bytes, rel_offset: int, *, max_len: int = 64) -> str | None:
    if rel_offset < 0 or rel_offset >= len(data):
        return None
    end = data.find(b"\x00", rel_offset)
    if end <= rel_offset:
        return None
    if end - rel_offset > max_len:
        return None
    try:
        text = data[rel_offset:end].decode("utf-8")
    except UnicodeDecodeError:
        return None
    text = text.strip()
    return text or None


def _record_identity_valid(data: bytes, rel_base: int) -> tuple[int, int, int, str] | None:
    need = rel_base + OFF_MEMBER_PROFILE_ID + 4
    if need > len(data):
        return None
    region = struct.unpack_from("<I", data, rel_base + OFF_MEMBER_REGION)[0]
    program = struct.unpack_from("<I", data, rel_base + OFF_MEMBER_PROGRAM)[0]
    realm = struct.unpack_from("<I", data, rel_base + OFF_MEMBER_REALM)[0]
    profile_id = struct.unpack_from("<I", data, rel_base + OFF_MEMBER_PROFILE_ID)[0]
    if program != LOBBY_PROGRAM_S2_TAG:
        return None
    if region < 1 or region > 9:
        return None
    if realm < 1 or realm > 2:
        return None
    if profile_id < MIN_PROFILE_ID or profile_id > MAX_PROFILE_ID:
        return None
    handle = handle_from_identity(region, realm, profile_id)
    if handle is None:
        return None
    return region, realm, profile_id, handle


def parse_lobby_member_record(
    data: bytes,
    *,
    record_base: int,
    rel_base: int,
) -> LobbyMemberRecord | None:
    identity = _record_identity_valid(data, rel_base)
    if identity is None:
        return None
    region, realm, profile_id, handle = identity
    internal_id = None
    if rel_base + OFF_MEMBER_INTERNAL_ID + 8 <= len(data):
        internal_id = struct.unpack_from("<Q", data, rel_base + OFF_MEMBER_INTERNAL_ID)[0]
    display_name = _read_member_display_raw(data, rel_base)
    team_name, nickname = parse_roster_display_name(display_name)
    if not team_name:
        team_name = _find_team_tag(data, rel_base)
    return LobbyMemberRecord(
        record_base=record_base,
        profile_address=record_base + OFF_MEMBER_PROFILE_ID,
        handle=handle,
        region_id=region,
        realm_id=realm,
        profile_id=profile_id,
        display_name=nickname or None,
        team_name=team_name,
        raw_display_name=display_name,
        internal_id=internal_id,
    )

def verify_lobby_profile_id_at(
    process_handle,
    profile_address: int,
    expected_handle: str,
) -> bool:
    parts = parse_handle_parts(expected_handle)
    if parts is None:
        return False
    blob = _read_memory(process_handle, profile_address, 4)
    if not blob or len(blob) < 4:
        return False
    profile_id = struct.unpack_from("<I", blob, 0)[0]
    return profile_id == parts.player_id


def verify_lobby_member_record_at(
    process_handle,
    record_base: int,
    expected_handle: str,
) -> bool:
    blob = _read_memory(process_handle, record_base, LOBBY_MEMBER_RECORD_SIZE)
    if not blob or len(blob) < OFF_MEMBER_PROFILE_ID + 4:
        return False
    identity = _record_identity_valid(blob, 0)
    if identity is None:
        return False
    _region, _realm, _profile_id, handle = identity
    return handle == expected_handle


def verify_lobby_name_utf8_at(
    process_handle,
    name_address: int,
    display_name: str,
) -> bool:
    needle = display_name.encode("utf-8")
    blob = _read_memory(process_handle, name_address, len(needle) + 4)
    if not blob or len(blob) < len(needle):
        return False
    if blob[: len(needle)] != needle:
        return False
    if len(blob) > len(needle) and blob[len(needle)] != 0:
        return False
    return True


def read_member_name_address(record_base: int) -> int:
    return record_base + OFF_MEMBER_NAME_UTF8


def find_lobby_roster_arrays_in_data(
    data: bytes,
    *,
    window_base: int,
    region_base: int,
    region_type: str,
    min_members: int = 2,
    max_members: int = 12,
    priority_handles: set[str] | None = None,
) -> list[ChannelRosterCluster]:
    if len(data) < LOBBY_MEMBER_RECORD_SIZE:
        return []

    clusters: list[ChannelRosterCluster] = []
    step = 4
    rel = 0
    limit = len(data) - LOBBY_MEMBER_RECORD_SIZE
    while rel <= limit:
        if _record_identity_valid(data, rel) is None:
            rel += step
            continue

        members: list[LobbyMemberRecord] = []
        index = 0
        while index < max_members:
            member_rel = rel + index * LOBBY_MEMBER_RECORD_SIZE
            if member_rel + OFF_MEMBER_PROFILE_ID + 4 > len(data):
                break
            record = parse_lobby_member_record(
                data,
                record_base=window_base + member_rel,
                rel_base=member_rel,
            )
            if record is None:
                break
            members.append(record)
            index += 1

        if len(members) >= min_members:
            handles = {item.handle for item in members}
            score = float(len(handles) * 28 + 45)
            notes = [
                "lobby_member_struct",
                f"stride=0x{LOBBY_MEMBER_RECORD_SIZE:X}",
                f"{len(handles)} members",
            ]
            if priority_handles and handles & priority_handles:
                score += 35.0
                notes.append("contains known room member")
            if region_type == "private":
                score += 25.0
                notes.append("private heap")
            span_start = members[0].record_base
            span_end = members[-1].record_base + LOBBY_MEMBER_RECORD_SIZE
            clusters.append(
                ChannelRosterCluster(
                    region_base=region_base,
                    span_start=span_start,
                    span_end=span_end,
                    members=tuple(
                        (item.profile_address, item.handle) for item in members
                    ),
                    member_count=len(handles),
                    region_type=region_type,
                    score=score,
                    notes=tuple(notes),
                )
            )
            rel += len(members) * LOBBY_MEMBER_RECORD_SIZE
            continue

        rel += step

    return clusters


def scan_lobby_struct_rosters(
    process_handle,
    *,
    known_handles: set[str] | None = None,
    min_members: int = 2,
    max_members: int = 12,
    time_budget_sec: float = 8.0,
    prefer_private: bool = True,
    chunk_size: int = 65536,
) -> list[ChannelRosterCluster]:
    """Scan process memory for SC2 lobby member struct arrays."""
    priority = known_handles or set()
    started = time.perf_counter()
    all_clusters: list[ChannelRosterCluster] = []

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
            read_size = min(chunk_size, region_size - offset)
            data = _read_memory(process_handle, region_base + offset, read_size)
            if not data:
                offset += read_size
                continue
            all_clusters.extend(
                find_lobby_roster_arrays_in_data(
                    data,
                    window_base=region_base + offset,
                    region_base=region_base,
                    region_type=region_type,
                    min_members=min_members,
                    max_members=max_members,
                    priority_handles=priority,
                )
            )
            offset += read_size

    return _dedupe_clusters(all_clusters)


def pick_struct_name_address(
    process_handle,
    cluster: ChannelRosterCluster,
    display_name: str,
) -> int | None:
    """Resolve inline UTF-8 name inside a lobby struct roster cluster."""
    if not cluster.notes or "lobby_member_struct" not in cluster.notes:
        return None
    target = display_name.strip()
    for profile_addr, _handle in cluster.members:
        record_base = profile_addr - OFF_MEMBER_PROFILE_ID
        name_addr = read_member_name_address(record_base)
        if verify_lobby_name_utf8_at(process_handle, name_addr, target):
            return name_addr
    return None


def profile_id_bytes_for_handle(handle: str) -> bytes | None:
    parts = parse_handle_parts(handle)
    if parts is None:
        return None
    return struct.pack("<I", parts.player_id)


def identity_prefix_bytes(region: int, realm: int) -> bytes:
    return (
        struct.pack("<I", region)
        + struct.pack("<I", LOBBY_PROGRAM_S2_TAG)
        + struct.pack("<I", realm)
    )


def find_profile_addresses_for_handle_in_data(
    data: bytes,
    *,
    window_base: int,
    expected_handle: str,
) -> list[int]:
    parts = parse_handle_parts(expected_handle)
    if parts is None:
        return []
    prefix = identity_prefix_bytes(parts.server_id, parts.realm_id)
    profile_bytes = struct.pack("<I", parts.player_id)
    hits: list[int] = []
    start = 0
    while True:
        rel = data.find(prefix, start)
        if rel < 0:
            break
        profile_rel = rel + (OFF_MEMBER_PROFILE_ID - OFF_MEMBER_REGION)
        if profile_rel + 4 <= len(data):
            if data[profile_rel : profile_rel + 4] == profile_bytes:
                hits.append(window_base + profile_rel)
        start = rel + 4
    return hits


def _find_roster_array_start(process_handle, anchor_base: int) -> int:
    """Walk backward from anchor until the first slot of the fixed-size lobby array."""
    start = anchor_base
    for step in range(1, LOBBY_UI_SLOT_COUNT):
        prev_base = anchor_base - step * LOBBY_MEMBER_RECORD_SIZE
        blob = _read_memory(process_handle, prev_base, LOBBY_MEMBER_RECORD_SIZE)
        if not blob:
            break
        if parse_lobby_member_record(blob, record_base=prev_base, rel_base=0) is None:
            break
        start = prev_base
    return start


def read_roster_members_at_base(
    process_handle,
    record_base: int,
    *,
    max_members: int = 12,
    max_backward: int = MAX_ROSTER_BACKWARD_SLOTS,
) -> list[tuple[int, LobbyMemberRecord]]:
    """Read up to ``LOBBY_UI_SLOT_COUNT`` lobby slots; returns (slot_index, record) pairs.

    ``slot_index`` is 0-based and matches SC2 UI slot 1..10 (slot_index + 1).
    Empty slots are skipped; occupied slots keep their absolute index even when
    earlier slots are empty.
    """
    _ = max_members, max_backward  # legacy kwargs kept for callers
    array_start = _find_roster_array_start(process_handle, record_base)
    blob = _read_memory(
        process_handle,
        array_start,
        LOBBY_MEMBER_RECORD_SIZE * LOBBY_UI_SLOT_COUNT,
    )
    if not blob:
        return []

    seen: set[str] = set()
    occupied: list[tuple[int, LobbyMemberRecord]] = []
    for slot_index in range(LOBBY_UI_SLOT_COUNT):
        rel = slot_index * LOBBY_MEMBER_RECORD_SIZE
        if rel + LOBBY_MEMBER_RECORD_SIZE > len(blob):
            break
        record = parse_lobby_member_record(
            blob,
            record_base=array_start + rel,
            rel_base=rel,
        )
        if record is None:
            continue
        if record.handle in seen:
            continue
        seen.add(record.handle)
        occupied.append((slot_index, record))
    return occupied


def host_in_roster_at_base(
    process_handle,
    record_base: int,
    host_handle: str,
) -> bool:
    """True when the roster array at ``record_base`` has a valid 440-byte row for host."""
    members = read_roster_members_at_base(process_handle, record_base)
    return any(item.handle == host_handle for _slot, item in members)


def scan_process_for_lobby_profile_handle(
    process_handle,
    expected_handle: str,
    *,
    time_budget_sec: float = 6.0,
    prefer_private: bool = True,
    chunk_size: int = 65536,
) -> list[int]:
    """Find profile_id field addresses for one handle using lobby struct layout."""
    started = time.perf_counter()
    hits: list[int] = []
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
            read_size = min(chunk_size, region_size - offset)
            data = _read_memory(process_handle, region_base + offset, read_size)
            if not data:
                offset += read_size
                continue
            hits.extend(
                find_profile_addresses_for_handle_in_data(
                    data,
                    window_base=region_base + offset,
                    expected_handle=expected_handle,
                )
            )
            offset += read_size
    return sorted(set(hits))
