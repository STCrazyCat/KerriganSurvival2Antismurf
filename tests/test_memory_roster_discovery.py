import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.lobby.memory_lobby_roster import (
    LOBBY_MEMBER_RECORD_SIZE,
    LOBBY_PROGRAM_S2_TAG,
    OFF_MEMBER_PROFILE_ID,
)
from antismurf.lobby.memory_roster_discovery import (
    DiscoveryPhase,
    RosterDiscoverySnapshot,
    analyze_roster_discovery,
    describe_profile_address,
    evaluate_roster_confirmation,
    profile_id_needles,
    scan_profile_field_addresses,
)


def test_profile_id_needles_three_bytes() -> None:
    needle, profile_id = profile_id_needles("5-S2-1-12208616", width=3)
    assert needle == bytes([0xE8, 0x49, 0xBA])
    assert profile_id == 12208616


def test_analyze_roster_discovery_prefers_vanished_in_room() -> None:
    class FakeHandle:
        pass

    record = bytearray(LOBBY_MEMBER_RECORD_SIZE)
    struct.pack_into("<I", record, 0x10, 5)
    struct.pack_into("<I", record, 0x14, LOBBY_PROGRAM_S2_TAG)
    struct.pack_into("<I", record, 0x18, 1)
    struct.pack_into("<I", record, OFF_MEMBER_PROFILE_ID, 12208616)
    base = 0x8000
    profile_addr = base + OFF_MEMBER_PROFILE_ID
    memory: dict[int, bytes] = {}

    import antismurf.lobby.memory_reader as mr
    import antismurf.lobby.memory_roster_discovery as rd
    import antismurf.lobby.memory_lobby_roster as lr

    original = mr._read_memory
    original_lr = lr._read_memory

    def fake_read(_handle, address, size):
        for mem_base, data in memory.items():
            if mem_base <= address < mem_base + len(data):
                rel = address - mem_base
                return data[rel : rel + size]
        return b""

    mr._read_memory = fake_read
    rd._read_memory = fake_read
    lr._read_memory = fake_read

    import antismurf.lobby.memory_probe as mp
    import antismurf.lobby.memory_roster_discovery as rd_mod

    original_locate = mp.locate_address

    def fake_locate(address, *, modules, process_handle=None):
        from antismurf.lobby.memory_probe import MemoryLocation

        return MemoryLocation(
            address=address,
            region_base=base,
            region_size=LOBBY_MEMBER_RECORD_SIZE,
            protect=0x04,
            region_type="private",
        )

    mp.locate_address = fake_locate
    rd_mod.locate_address = fake_locate
    try:
        memory[base] = bytes(record)
        snapshots = [
            RosterDiscoverySnapshot(
                phase=DiscoveryPhase.BASELINE,
                timestamp=0.0,
                host_handle="5-S2-1-12208616",
                profile_addresses=set(),
            ),
            RosterDiscoverySnapshot(
                phase=DiscoveryPhase.IN_ROOM,
                timestamp=1.0,
                host_handle="5-S2-1-12208616",
                profile_addresses={profile_addr},
            ),
        ]
        report_in_only = analyze_roster_discovery(
            FakeHandle(),
            host_handle="5-S2-1-12208616",
            snapshots=snapshots,
        )
        assert report_in_only.best is not None
        assert report_in_only.best.record_base == base

        del memory[base]
        snapshots.append(
            RosterDiscoverySnapshot(
                phase=DiscoveryPhase.AFTER_EXIT,
                timestamp=2.0,
                host_handle="5-S2-1-12208616",
                profile_addresses=set(),
            )
        )
        report_out = analyze_roster_discovery(
            FakeHandle(),
            host_handle="5-S2-1-12208616",
            snapshots=snapshots,
        )
        assert report_out.best is not None
        assert report_out.best.vanished_on_exit
        assert report_out.best.score >= report_in_only.best.score
        confirmation = evaluate_roster_confirmation(report_out)
        assert confirmation.confirmed
        assert confirmation.confidence == "high"
        assert confirmation.record_base == base
    finally:
        mp.locate_address = original_locate
        rd_mod.locate_address = original_locate
        mr._read_memory = original
        lr._read_memory = original_lr


def test_scan_profile_field_addresses_mock() -> None:
    class FakeHandle:
        pass

    needle, _profile = profile_id_needles("5-S2-1-6738824", width=3)
    blob = b"\x00" * 32 + needle + b"\x00"
    regions = [(0x10000, len(blob))]

    import antismurf.lobby.memory_reader as mr
    import antismurf.lobby.memory_roster_discovery as rd

    original_iter = rd._iter_readable_regions_typed
    original_read = rd._read_memory
    original_mr = mr._read_memory

    rd._iter_readable_regions_typed = lambda _h: iter(
        [(0x10000, len(blob), "private")]
    )

    def fake_read(_handle, address, size):
        if address >= 0x10000 and address < 0x10000 + len(blob):
            rel = address - 0x10000
            return blob[rel : rel + size]
        return b""

    rd._read_memory = fake_read
    mr._read_memory = fake_read
    try:
        hits = scan_profile_field_addresses(
            FakeHandle(),
            "5-S2-1-6738824",
            time_budget_sec=1.0,
        )
        assert len(hits) == 1
        assert hits[0].address == 0x10000 + 32
    finally:
        rd._iter_readable_regions_typed = original_iter
        rd._read_memory = original_read
        mr._read_memory = original_mr


def test_describe_profile_address_heap_offset() -> None:
    profile_addr = 0x2A6B67EDC78
    record_base = profile_addr - OFF_MEMBER_PROFILE_ID
    ce_module = 0x7FF68EB50000
    current_module = 0x7FF690000000

    import antismurf.lobby.memory_roster_discovery as rd

    original_build = rd.build_module_map
    original_locate = rd.locate_address

    rd.build_module_map = lambda _pid: [
        type("Mod", (), {"name": "SC2_x64.exe", "base": current_module, "size": 0x5000000})()
    ]

    from antismurf.lobby.memory_probe import MemoryLocation

    rd.locate_address = lambda _addr, **kwargs: MemoryLocation(
        address=profile_addr,
        region_base=0x2A6B60000000,
        region_size=0x1000000,
        protect=0x04,
        region_type="private",
    )
    try:
        lines = describe_profile_address(
            object(),
            profile_addr,
            pid=1234,
            ce_module_base=ce_module,
        )
        text = "\n".join(lines)
        assert f"0x{record_base:X}" in text
        assert "private" in text
        assert f"0x{ce_module:X}" in text
        assert "ASLR" in text or "漂移" in text
        assert "动态堆" in text
    finally:
        rd.build_module_map = original_build
        rd.locate_address = original_locate
