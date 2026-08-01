import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.lobby.memory_lobby_roster import (
    LOBBY_MEMBER_RECORD_SIZE,
    LOBBY_PROGRAM_S2_TAG,
    OFF_MEMBER_NAME_UTF8,
    OFF_MEMBER_PROFILE_ID,
    find_lobby_roster_arrays_in_data,
    find_profile_addresses_for_handle_in_data,
    parse_lobby_member_record,
    parse_roster_display_name,
    profile_id_bytes_for_handle,
    read_roster_members_at_base,
    verify_lobby_member_record_at,
    verify_lobby_name_utf8_at,
    verify_lobby_profile_id_at,
)


def _build_member_record(
    *,
    profile_id: int,
    display_name: str,
    region: int = 5,
    realm: int = 1,
    name_offset: int = OFF_MEMBER_NAME_UTF8,
    team_name: str | None = None,
    team_offset: int = 0x40,
) -> bytes:
    record = bytearray(LOBBY_MEMBER_RECORD_SIZE)
    struct.pack_into("<Q", record, 0x00, 0x000002A6E329D740)
    struct.pack_into("<Q", record, 0x08, 0x0A124E)
    struct.pack_into("<I", record, 0x10, region)
    struct.pack_into("<I", record, 0x14, LOBBY_PROGRAM_S2_TAG)
    struct.pack_into("<I", record, 0x18, realm)
    struct.pack_into("<I", record, OFF_MEMBER_PROFILE_ID, profile_id)
    if team_name:
        team_bytes = f"<{team_name}>".encode("utf-8")
        record[team_offset : team_offset + len(team_bytes)] = team_bytes
    name_bytes = display_name.encode("utf-8")
    record[name_offset : name_offset + len(name_bytes)] = name_bytes
    return bytes(record)


def test_parse_lobby_member_record_from_ce_layout() -> None:
    record = _build_member_record(
        profile_id=6738824,
        display_name="大主教阿塔尼斯#251",
        name_offset=0x48,
    )
    parsed = parse_lobby_member_record(record, record_base=0x2A6B67EDC58, rel_base=0)
    assert parsed is not None
    assert parsed.handle == "5-S2-1-6738824"
    assert parsed.profile_address == 0x2A6B67EDC58 + OFF_MEMBER_PROFILE_ID
    assert parsed.display_name == "大主教阿塔尼斯"
    assert parsed.team_name is None
    assert parsed.raw_display_name == "大主教阿塔尼斯#251"


def test_parse_lobby_member_record_reads_from_0x48_not_truncated_0x54() -> None:
    record = _build_member_record(
        profile_id=6738824,
        display_name="大主教阿塔尼斯#251",
        name_offset=0x48,
    )
    # Legacy +0x54 read would start mid-string and yield "塔尼斯#251".
    parsed = parse_lobby_member_record(record, record_base=0x1000, rel_base=0)
    assert parsed is not None
    assert parsed.display_name == "大主教阿塔尼斯"
    assert parsed.display_name != "塔尼斯#251"


def test_parse_roster_display_name_team_prefix() -> None:
    team, nick = parse_roster_display_name("<谁在黑我>大主教阿塔尼斯")
    assert team == "谁在黑我"
    assert nick == "大主教阿塔尼斯"

    team, nick = parse_roster_display_name("<谁在黑我>大主教阿塔尼斯#251")
    assert team == "谁在黑我"
    assert nick == "大主教阿塔尼斯"

def test_parse_roster_display_name_separate_team_field() -> None:
    record = _build_member_record(
        profile_id=6738824,
        display_name="大主教阿塔尼斯#251",
        name_offset=0x48,
        team_name="谁在黑我",
        team_offset=0x34,
    )
    parsed = parse_lobby_member_record(record, record_base=0x1000, rel_base=0)
    assert parsed is not None
    assert parsed.team_name == "谁在黑我"
    assert parsed.display_name == "大主教阿塔尼斯"


def test_parse_roster_display_name_combined_in_one_field() -> None:
    record = _build_member_record(
        profile_id=12208616,
        display_name="<谁在黑我>大主教阿塔尼斯",
        name_offset=0x48,
    )
    parsed = parse_lobby_member_record(record, record_base=0x1000, rel_base=0)
    assert parsed is not None
    assert parsed.team_name == "谁在黑我"
    assert parsed.display_name == "大主教阿塔尼斯"
    assert parsed.raw_display_name == "<谁在黑我>大主教阿塔尼斯"


def test_read_roster_members_includes_slots_before_anchor() -> None:
    guest = _build_member_record(profile_id=1111111, display_name="EarlierGuest")
    host = _build_member_record(profile_id=6738824, display_name="HostPlayer")
    after = _build_member_record(profile_id=2222222, display_name="LaterGuest")
    slot0 = 0x10000
    host_base = slot0 + LOBBY_MEMBER_RECORD_SIZE
    memory = {
        slot0: guest,
        host_base: host,
        host_base + LOBBY_MEMBER_RECORD_SIZE: after,
    }

    class FakeHandle:
        pass

    import antismurf.lobby.memory_lobby_roster as lr

    original = lr._read_memory

    def fake_read_simple(_handle, address, size):
        end = address + size
        parts: list[tuple[int, bytes]] = []
        for mem_base, data in memory.items():
            mem_end = mem_base + len(data)
            if mem_end <= address or mem_base >= end:
                continue
            rel_start = max(0, address - mem_base)
            rel_end = min(len(data), end - mem_base)
            parts.append((max(mem_base, address), data[rel_start:rel_end]))
        if not parts:
            return b""
        parts.sort(key=lambda item: item[0])
        return b"".join(item[1] for item in parts)

    lr._read_memory = fake_read_simple
    try:
        members = read_roster_members_at_base(FakeHandle(), host_base)
        assert len(members) == 3
        assert members[0][0] == 0
        assert members[0][1].handle == "5-S2-1-1111111"
        assert members[1][0] == 1
        assert members[1][1].handle == "5-S2-1-6738824"
        assert members[2][0] == 2
        assert members[2][1].handle == "5-S2-1-2222222"
    finally:
        lr._read_memory = original


def test_find_two_member_struct_array() -> None:
    record1 = _build_member_record(
        profile_id=6738824,
        display_name="大主教阿塔尼斯#251",
    )
    record2 = _build_member_record(
        profile_id=12208616,
        display_name="无敌感染者#465",
    )
    blob = record1 + record2
    clusters = find_lobby_roster_arrays_in_data(
        blob,
        window_base=0x10000,
        region_base=0x10000,
        region_type="private",
        min_members=2,
        priority_handles={"5-S2-1-6738824", "5-S2-1-12208616"},
    )
    assert len(clusters) == 1
    cluster = clusters[0]
    assert cluster.member_count == 2
    assert cluster.contains_handle("5-S2-1-6738824")
    assert cluster.contains_handle("5-S2-1-12208616")
    assert "lobby_member_struct" in cluster.notes
    assert cluster.score >= 70.0


def test_profile_id_bytes_for_handle() -> None:
    assert profile_id_bytes_for_handle("5-S2-1-12208616") == bytes(
        [0xE8, 0x49, 0xBA, 0x00]
    )


def test_verify_lobby_profile_and_name_with_mock() -> None:
    record = _build_member_record(
        profile_id=12208616,
        display_name="无敌感染者#465",
    )
    base = 0x5000

    class FakeHandle:
        pass

    import antismurf.lobby.memory_lobby_roster as lr
    import antismurf.lobby.memory_reader as mr

    memory = {base: record}

    def fake_read(_handle, address, size):
        for base_addr, data in memory.items():
            if base_addr <= address < base_addr + len(data):
                rel = address - base_addr
                return data[rel : rel + size]
        return b""

    original_mr = mr._read_memory
    original_lr = lr._read_memory
    mr._read_memory = fake_read
    lr._read_memory = fake_read
    try:
        profile_addr = base + OFF_MEMBER_PROFILE_ID
        assert verify_lobby_profile_id_at(
            FakeHandle(), profile_addr, "5-S2-1-12208616"
        )
        name_addr = base + OFF_MEMBER_NAME_UTF8
        assert verify_lobby_name_utf8_at(FakeHandle(), name_addr, "无敌感染者#465")
        assert verify_lobby_member_record_at(
            FakeHandle(), base, "5-S2-1-12208616"
        )
    finally:
        mr._read_memory = original_mr
        lr._read_memory = original_lr


def test_find_profile_addresses_for_handle_in_data() -> None:
    record = _build_member_record(
        profile_id=12208616,
        display_name="无敌感染者#465",
    )
    hits = find_profile_addresses_for_handle_in_data(
        record,
        window_base=0x2000,
        expected_handle="5-S2-1-12208616",
    )
    assert hits == [0x2000 + OFF_MEMBER_PROFILE_ID]


def test_rejects_standard_triplet_without_s2_tag() -> None:
    record = bytearray(LOBBY_MEMBER_RECORD_SIZE)
    struct.pack_into("<I", record, 0x10, 5)
    struct.pack_into("<I", record, 0x14, 2)
    struct.pack_into("<I", record, 0x18, 1)
    struct.pack_into("<I", record, OFF_MEMBER_PROFILE_ID, 12208616)
    assert parse_lobby_member_record(bytes(record), record_base=0x1000, rel_base=0) is None
