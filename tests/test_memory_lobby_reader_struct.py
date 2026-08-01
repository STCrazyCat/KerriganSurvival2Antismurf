import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.config.settings import AppConfig
from antismurf.lobby.memory_lobby_auto_confirm import (
    LobbyAutoConfirmSnapshot,
    LobbyMemberView,
    LobbyPhase,
)
from antismurf.lobby.memory_lobby_reader import MemoryLobbyReader
from antismurf.lobby.memory_lobby_roster import (
    LOBBY_MEMBER_RECORD_SIZE,
    LOBBY_PROGRAM_S2_TAG,
    OFF_MEMBER_PROFILE_ID,
)
from antismurf.lobby.probe_calibration import CalibratedProfile


class FakeHandle:
    pass


class FakeAutoConfirmSession:
    def __init__(self, snap: LobbyAutoConfirmSnapshot) -> None:
        self._snap = snap

    def tick(self, *, force_rescan: bool = False) -> LobbyAutoConfirmSnapshot:
        return self._snap


def _build_record(profile_id: int, name: str) -> bytearray:
    record = bytearray(LOBBY_MEMBER_RECORD_SIZE)
    struct.pack_into("<I", record, 0x10, 5)
    struct.pack_into("<I", record, 0x14, LOBBY_PROGRAM_S2_TAG)
    struct.pack_into("<I", record, 0x18, 1)
    struct.pack_into("<I", record, OFF_MEMBER_PROFILE_ID, profile_id)
    encoded = name.encode("utf-8")
    record[0x54 : 0x54 + len(encoded)] = encoded
    return record


def test_memory_lobby_reader_roster_mode_in_room() -> None:
    base = 0x1F62EF034F0
    host = "5-S2-1-6738824"
    guest_handle = "5-S2-1-12208616"

    import antismurf.lobby.memory_lobby_reader as mlr
    import antismurf.lobby.sc2_process as sp

    original_open = sp.open_process_for_read
    original_close = sp.close_process
    original_list = sp.list_sc2_pids
    original_resolve = sp.resolve_sc2_pid
    original_ensure = MemoryLobbyReader._ensure_mode6_session

    snap = LobbyAutoConfirmSnapshot(
        tick=1,
        timestamp=0.0,
        host_handle=host,
        host_anchor_ok=True,
        record_base=base,
        record_base_source="profile_scan",
        phase=LobbyPhase.IN_ROOM,
        in_room=True,
        room_created=True,
        member_count=2,
        members=[
            LobbyMemberView(
                slot=0,
                handle=host,
                display_name="HostName",
                record_base=base,
                profile_address=base + OFF_MEMBER_PROFILE_ID,
                is_host=True,
            ),
            LobbyMemberView(
                slot=1,
                handle=guest_handle,
                display_name="GuestName",
                record_base=base + LOBBY_MEMBER_RECORD_SIZE,
                profile_address=base + LOBBY_MEMBER_RECORD_SIZE + OFF_MEMBER_PROFILE_ID,
                is_host=False,
            ),
        ],
    )

    sp.open_process_for_read = lambda _pid: FakeHandle()
    sp.close_process = lambda _h: None
    sp.list_sc2_pids = lambda *_a, **_k: [4242]
    sp.resolve_sc2_pid = lambda **_k: 4242
    mlr.list_sc2_pids = sp.list_sc2_pids
    mlr.resolve_sc2_pid = sp.resolve_sc2_pid
    mlr.open_process_for_read = sp.open_process_for_read
    mlr.close_process = sp.close_process
    MemoryLobbyReader._ensure_mode6_session = lambda self, _pid: FakeAutoConfirmSession(snap)

    config = AppConfig(
        memory_enabled=True,
        memory_scan_mode="roster",
        host_handle="5-S2-1-WRONG",
        target_maps=("凯瑞甘生存2",),
    )
    calibration = CalibratedProfile(
        expected_handle=host,
        expected_name="HostName",
        name_address=base + 0x54,
        handle_address=base + OFF_MEMBER_PROFILE_ID,
        struct_base=base,
        name_offset=0x54,
        handle_offset=OFF_MEMBER_PROFILE_ID,
    )
    reader = MemoryLobbyReader(config, calibration=calibration)
    try:
        snapshot = reader.read_lobby_snapshot()
        assert snapshot.error is None
        assert snapshot.is_local_host is True
        assert snapshot.map_name == "凯瑞甘生存2"
        assert len(snapshot.handles) == 2
        assert snapshot.handles[0].handle == host
        assert snapshot.handles[1].display_name == "GuestName"
        assert reader.roster_state.in_room is True
        assert reader.roster_state.record_base == base
        assert snapshot.local_handle == host
    finally:
        MemoryLobbyReader._ensure_mode6_session = original_ensure
        sp.open_process_for_read = original_open
        sp.close_process = original_close
        sp.list_sc2_pids = original_list
        sp.resolve_sc2_pid = original_resolve
        mlr.list_sc2_pids = original_list
        mlr.resolve_sc2_pid = original_resolve
        mlr.open_process_for_read = original_open
        mlr.close_process = original_close


def test_memory_lobby_reader_ignores_config_host_handle_in_roster_mode() -> None:
    base = 0x1F62EF034F0
    host = "5-S2-1-6738824"

    import antismurf.lobby.memory_lobby_reader as mlr
    import antismurf.lobby.sc2_process as sp

    original_open = sp.open_process_for_read
    original_close = sp.close_process
    original_list = sp.list_sc2_pids
    original_resolve = sp.resolve_sc2_pid
    original_ensure = MemoryLobbyReader._ensure_mode6_session

    snap = LobbyAutoConfirmSnapshot(
        tick=1,
        timestamp=0.0,
        host_handle=host,
        host_anchor_ok=True,
        record_base=base,
        record_base_source="profile_scan",
        phase=LobbyPhase.OUT_OF_ROOM,
        in_room=False,
        room_created=False,
        member_count=0,
        members=[],
    )

    sp.open_process_for_read = lambda _pid: FakeHandle()
    sp.close_process = lambda _h: None
    sp.list_sc2_pids = lambda *_a, **_k: [4242]
    sp.resolve_sc2_pid = lambda **_k: 4242
    mlr.list_sc2_pids = sp.list_sc2_pids
    mlr.resolve_sc2_pid = sp.resolve_sc2_pid
    MemoryLobbyReader._ensure_mode6_session = lambda self, _pid: FakeAutoConfirmSession(snap)

    config = AppConfig(
        memory_enabled=True,
        memory_scan_mode="roster",
        host_handle="5-S2-1-12208616",
    )
    reader = MemoryLobbyReader(config)
    try:
        snapshot = reader.read_lobby_snapshot()
        assert snapshot.error is None
        assert snapshot.handles == []
        assert snapshot.local_handle == host
    finally:
        MemoryLobbyReader._ensure_mode6_session = original_ensure
        sp.open_process_for_read = original_open
        sp.close_process = original_close
        sp.list_sc2_pids = original_list
        sp.resolve_sc2_pid = original_resolve
