import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.lobby.memory_lobby_auto_confirm import (
    LobbyAutoConfirmSession,
    LobbyPhase,
    RoomPresenceDebouncer,
    evaluate_lobby_snapshot,
    resolve_record_base,
)
from antismurf.lobby.memory_lobby_roster import (
    LOBBY_MEMBER_RECORD_SIZE,
    LOBBY_PROGRAM_S2_TAG,
    OFF_MEMBER_PROFILE_ID,
    read_roster_members_at_base,
)
from antismurf.lobby.probe_calibration import CalibratedProfile


class FakeHandle:
    pass


def _build_record(profile_id: int, name: str) -> bytearray:
    record = bytearray(LOBBY_MEMBER_RECORD_SIZE)
    struct.pack_into("<I", record, 0x10, 5)
    struct.pack_into("<I", record, 0x14, LOBBY_PROGRAM_S2_TAG)
    struct.pack_into("<I", record, 0x18, 1)
    struct.pack_into("<I", record, OFF_MEMBER_PROFILE_ID, profile_id)
    encoded = name.encode("utf-8")
    record[0x54 : 0x54 + len(encoded)] = encoded
    return record


def test_read_roster_members_at_base_two_slots() -> None:
    base = 0x2A6B67EDC58
    blob = bytes(_build_record(6738824, "Host")) + bytes(_build_record(12208616, "Guest"))
    memory = {base: blob}

    import antismurf.lobby.memory_lobby_roster as lr

    original = lr._read_memory

    def fake_read(_handle, address, size):
        if address in memory:
            return memory[address][:size]
        return b""

    lr._read_memory = fake_read
    try:
        members = read_roster_members_at_base(FakeHandle(), base)
        assert len(members) == 2
        assert members[0][0] == 0
        assert members[0][1].handle == "5-S2-1-6738824"
        assert members[1][0] == 1
        assert members[1][1].display_name == "Guest"
    finally:
        lr._read_memory = original


def test_evaluate_lobby_snapshot_room_created() -> None:
    from antismurf.lobby.memory_lobby_roster import parse_lobby_member_record

    record = bytes(_build_record(6738824, "Host"))
    member = parse_lobby_member_record(record, record_base=0x1000, rel_base=0)
    assert member is not None
    phase, in_room, room_created = evaluate_lobby_snapshot(
        host_handle="5-S2-1-6738824",
        record_base=0x1000,
        members=[member],
    )
    assert phase == LobbyPhase.IN_ROOM
    assert in_room is True
    assert room_created is True


def test_host_in_roster_at_base_requires_valid_440_bytes() -> None:
    import antismurf.lobby.memory_lobby_roster as lr
    import antismurf.lobby.memory_reader as mr
    from antismurf.lobby.memory_lobby_roster import host_in_roster_at_base

    base = 0x8000
    host = "5-S2-1-6738824"
    memory: dict[int, bytes] = {base: bytes(LOBBY_MEMBER_RECORD_SIZE)}

    original_lr = lr._read_memory
    original_mr = mr._read_memory

    def fake_read(_handle, address, size):
        for mem_base, data in memory.items():
            if mem_base <= address < mem_base + len(data):
                rel = address - mem_base
                return data[rel : rel + size]
        return b""

    lr._read_memory = fake_read
    mr._read_memory = fake_read
    try:
        assert host_in_roster_at_base(FakeHandle(), base, host) is False
        memory[base] = bytes(_build_record(6738824, "Host"))
        assert host_in_roster_at_base(FakeHandle(), base, host) is True
    finally:
        lr._read_memory = original_lr
        mr._read_memory = original_mr


def test_resolve_record_base_empty_struct_returns_none() -> None:
    import antismurf.lobby.memory_lobby_roster as lr
    import antismurf.lobby.memory_reader as mr

    base = 0x9000
    host = "5-S2-1-6738824"
    memory = {base: bytes(LOBBY_MEMBER_RECORD_SIZE)}

    original_lr = lr._read_memory
    original_mr = mr._read_memory

    def fake_read(_handle, address, size):
        for mem_base, data in memory.items():
            if mem_base <= address < mem_base + len(data):
                rel = address - mem_base
                return data[rel : rel + size]
        return b""

    lr._read_memory = fake_read
    mr._read_memory = fake_read

    import antismurf.lobby.memory_lobby_auto_confirm as ac

    original_scan = ac.scan_process_for_lobby_profile_handle
    original_struct = ac.scan_lobby_struct_rosters
    ac.scan_process_for_lobby_profile_handle = lambda *_a, **_k: []
    ac.scan_lobby_struct_rosters = lambda *_a, **_k: []
    try:
        profile = CalibratedProfile(
            expected_handle=host,
            expected_name="Host",
            name_address=base + 0x54,
            handle_address=base + OFF_MEMBER_PROFILE_ID,
            struct_base=base,
            name_offset=0x54,
            handle_offset=OFF_MEMBER_PROFILE_ID,
        )
        resolved, source = resolve_record_base(FakeHandle(), host, calibration=profile)
        assert resolved is None
        assert source == "none"
    finally:
        ac.scan_process_for_lobby_profile_handle = original_scan
        ac.scan_lobby_struct_rosters = original_struct
        lr._read_memory = original_lr
        mr._read_memory = original_mr


def test_session_clears_when_roster_struct_cleared() -> None:
    base = 0x8000
    host = "5-S2-1-6738824"
    memory: dict[int, bytes] = {base: bytes(_build_record(6738824, "Host"))}

    import antismurf.lobby.memory_lobby_auto_confirm as ac
    import antismurf.lobby.memory_lobby_roster as lr
    import antismurf.lobby.memory_reader as mr

    original_lr = lr._read_memory
    original_mr = mr._read_memory
    original_host = ac.read_host_handle_from_process

    def fake_read(_handle, address, size):
        for mem_base, data in memory.items():
            if mem_base <= address < mem_base + len(data):
                return data[address - mem_base : address - mem_base + size]
        return b""

    lr._read_memory = fake_read
    mr._read_memory = fake_read
    ac.read_host_handle_from_process = lambda *_args, **_kwargs: type(
        "Anchor",
        (),
        {
            "handle": host,
            "module_base": 0x7FF600000000,
            "module_label": "SC2_x64.exe+0x3E2F340",
        },
    )()

    original_scan = ac.scan_process_for_lobby_profile_handle
    original_struct = ac.scan_lobby_struct_rosters
    ac.scan_process_for_lobby_profile_handle = lambda *_a, **_k: []
    ac.scan_lobby_struct_rosters = lambda *_a, **_k: []

    profile = CalibratedProfile(
        expected_handle=host,
        expected_name="Host",
        name_address=base + 0x54,
        handle_address=base + OFF_MEMBER_PROFILE_ID,
        struct_base=base,
        name_offset=0x54,
        handle_offset=OFF_MEMBER_PROFILE_ID,
    )
    session = LobbyAutoConfirmSession(
        FakeHandle(),
        pid=1,
        calibration=profile,
        enter_confirm_ticks=1,
        exit_confirm_ticks=2,
    )
    first = session.tick()
    assert first.in_room is True

    memory[base] = bytes(LOBBY_MEMBER_RECORD_SIZE)
    second = session.tick()
    assert second.in_room is True
    third = session.tick()
    assert third.in_room is False
    assert session._cached_base is None

    ac.read_host_handle_from_process = original_host
    ac.scan_process_for_lobby_profile_handle = original_scan
    ac.scan_lobby_struct_rosters = original_struct
    lr._read_memory = original_lr
    mr._read_memory = original_mr


def test_session_single_miss_does_not_exit() -> None:
    base = 0x8000
    host = "5-S2-1-6738824"
    good = bytes(_build_record(6738824, "Host"))
    empty = bytes(LOBBY_MEMBER_RECORD_SIZE)
    memory: dict[int, bytes] = {base: good}

    import antismurf.lobby.memory_lobby_auto_confirm as ac
    import antismurf.lobby.memory_lobby_roster as lr
    import antismurf.lobby.memory_reader as mr

    original_lr = lr._read_memory
    original_mr = mr._read_memory
    original_host = ac.read_host_handle_from_process

    def fake_read(_handle, address, size):
        for mem_base, data in memory.items():
            if mem_base <= address < mem_base + len(data):
                return data[address - mem_base : address - mem_base + size]
        return b""

    lr._read_memory = fake_read
    mr._read_memory = fake_read
    ac.read_host_handle_from_process = lambda *_args, **_kwargs: type(
        "Anchor",
        (),
        {
            "handle": host,
            "module_base": 0x7FF600000000,
            "module_label": "SC2_x64.exe+0x3E2F340",
        },
    )()

    original_scan = ac.scan_process_for_lobby_profile_handle
    original_struct = ac.scan_lobby_struct_rosters
    ac.scan_process_for_lobby_profile_handle = lambda *_a, **_k: []
    ac.scan_lobby_struct_rosters = lambda *_a, **_k: []

    profile = CalibratedProfile(
        expected_handle=host,
        expected_name="Host",
        name_address=base + 0x54,
        handle_address=base + OFF_MEMBER_PROFILE_ID,
        struct_base=base,
        name_offset=0x54,
        handle_offset=OFF_MEMBER_PROFILE_ID,
    )
    session = LobbyAutoConfirmSession(
        FakeHandle(),
        pid=1,
        calibration=profile,
        enter_confirm_ticks=1,
        exit_confirm_ticks=3,
    )
    assert session.tick().in_room is True

    memory[base] = empty
    miss = session.tick()
    assert miss.in_room is True
    assert miss.raw_in_room is False
    assert miss.member_count == 1
    assert session._cached_base == base

    memory[base] = good
    recover = session.tick()
    assert recover.in_room is True
    assert recover.raw_in_room is True

    ac.read_host_handle_from_process = original_host
    ac.scan_process_for_lobby_profile_handle = original_scan
    ac.scan_lobby_struct_rosters = original_struct
    lr._read_memory = original_lr
    mr._read_memory = original_mr


def test_room_presence_debouncer_hysteresis() -> None:
    debouncer = RoomPresenceDebouncer(enter_required=2, exit_required=3)
    assert debouncer.update(False) is False
    assert debouncer.update(True) is False
    assert debouncer.update(True) is True
    assert debouncer.update(False) is True
    assert debouncer.update(False) is True
    assert debouncer.update(False) is False


def test_auto_confirm_session_detects_join() -> None:
    base = 0x8000
    host = "5-S2-1-6738824"
    memory: dict[int, bytes] = {base: bytes(_build_record(6738824, "Host"))}

    import antismurf.lobby.memory_lobby_auto_confirm as ac
    import antismurf.lobby.memory_lobby_roster as lr
    import antismurf.lobby.memory_reader as mr

    original_lr = lr._read_memory
    original_mr = mr._read_memory
    original_host = ac.read_host_handle_from_process

    def fake_read(_handle, address, size):
        for mem_base, data in memory.items():
            if mem_base <= address < mem_base + len(data):
                rel = address - mem_base
                return data[rel : rel + size]
        return b""

    lr._read_memory = fake_read
    mr._read_memory = fake_read

    ac.read_host_handle_from_process = lambda *_args, **_kwargs: type(
        "Anchor",
        (),
        {
            "handle": host,
            "module_base": 0x7FF600000000,
            "module_label": "SC2_x64.exe+0x3E2F340",
        },
    )()

    profile = CalibratedProfile(
        expected_handle=host,
        expected_name="Host",
        name_address=base + 0x54,
        handle_address=base + OFF_MEMBER_PROFILE_ID,
        struct_base=base,
        name_offset=0x54,
        handle_offset=OFF_MEMBER_PROFILE_ID,
    )
    session = LobbyAutoConfirmSession(FakeHandle(), pid=1, calibration=profile, enter_confirm_ticks=1)
    first = session.tick()
    assert first.in_room is True
    assert first.room_created is True

    memory[base] = bytes(_build_record(6738824, "Host")) + bytes(
        _build_record(12208616, "Guest")
    )
    second = session.tick()
    assert second.member_count == 2
    assert any("玩家加入" in event for event in session.events)

    ac.read_host_handle_from_process = original_host
    lr._read_memory = original_lr
    mr._read_memory = original_mr


def test_calibration_skipped_when_handle_mismatch() -> None:
    import antismurf.lobby.memory_lobby_roster as lr
    import antismurf.lobby.memory_reader as mr
    from antismurf.lobby.memory_lobby_auto_confirm import resolve_record_base

    base = 0x9000
    live_host = "5-S2-1-12208616"
    memory = {base: bytes(_build_record(6738824, "Host"))}

    original_lr = lr._read_memory
    original_mr = mr._read_memory

    def fake_read(_handle, address, size):
        for mem_base, data in memory.items():
            if mem_base <= address < mem_base + len(data):
                rel = address - mem_base
                return data[rel : rel + size]
        return b""

    lr._read_memory = fake_read
    mr._read_memory = fake_read

    import antismurf.lobby.memory_lobby_auto_confirm as ac

    original_scan = ac.scan_process_for_lobby_profile_handle
    original_struct = ac.scan_lobby_struct_rosters
    ac.scan_process_for_lobby_profile_handle = lambda *_a, **_k: []
    ac.scan_lobby_struct_rosters = lambda *_a, **_k: []
    try:
        profile = CalibratedProfile(
            expected_handle="5-S2-1-6738824",
            expected_name="Host",
            name_address=base + 0x54,
            handle_address=base + OFF_MEMBER_PROFILE_ID,
            struct_base=base,
            name_offset=0x54,
            handle_offset=OFF_MEMBER_PROFILE_ID,
        )
        resolved, source = resolve_record_base(
            FakeHandle(), live_host, calibration=profile
        )
        assert resolved is None
        assert source == "none"
    finally:
        ac.scan_process_for_lobby_profile_handle = original_scan
        ac.scan_lobby_struct_rosters = original_struct
        lr._read_memory = original_lr
        mr._read_memory = original_mr


def test_resolve_record_base_uses_calibration() -> None:
    base = 0x9000
    host = "5-S2-1-6738824"
    memory = {base: bytes(_build_record(6738824, "Host"))}

    import antismurf.lobby.memory_lobby_roster as lr
    import antismurf.lobby.memory_reader as mr

    original_lr = lr._read_memory
    original_mr = mr._read_memory

    def fake_read(_handle, address, size):
        if address in memory:
            return memory[address][:size]
        for mem_base, data in memory.items():
            if mem_base <= address < mem_base + len(data):
                rel = address - mem_base
                return data[rel : rel + size]
        return b""

    lr._read_memory = fake_read
    mr._read_memory = fake_read
    try:
        profile = CalibratedProfile(
            expected_handle=host,
            expected_name="Host",
            name_address=base + 0x54,
            handle_address=base + OFF_MEMBER_PROFILE_ID,
            name_encoding="utf8_z",
            handle_encoding="profile_triplet",
            struct_base=base,
            name_offset=0x54,
            handle_offset=OFF_MEMBER_PROFILE_ID,
        )
        resolved, source = resolve_record_base(FakeHandle(), host, calibration=profile)
        assert resolved == base
        assert source == "calibration"
    finally:
        lr._read_memory = original_lr
        mr._read_memory = original_mr
