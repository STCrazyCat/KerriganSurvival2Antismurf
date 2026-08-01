import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.config.settings import AppConfig
from antismurf.lobby import lobby_handles as lh
from antismurf.lobby.memory_formats import (
    StringEncoding,
    extract_handle_hits,
    scan_sc2_byte_strings,
    scan_utf16le_null_strings,
)
from antismurf.lobby.memory_profile_store import MemoryProfileStore


def test_extract_handle_hits_ascii_only() -> None:
    data = b"\x00prefix 5-S2-1-1234567\x00"
    hits = extract_handle_hits(data)
    assert len(hits) == 1
    assert hits[0][1] == "5-S2-1-1234567"
    assert hits[0][2] == StringEncoding.ASCII_Z


def test_scan_utf16le_player_name() -> None:
    name = "凯瑞甘玩家"
    data = name.encode("utf-16-le") + b"\x00\x00"
    decoded = scan_utf16le_null_strings(data)
    assert any(item.text == name for item in decoded)


def test_scan_sc2_byte_string_format() -> None:
    payload = b"Pille"
    raw_len = len(payload) << 1
    data = bytes([0x0A, raw_len]) + payload
    decoded = scan_sc2_byte_strings(data)
    assert decoded and decoded[0].text == "Pille"
    assert decoded[0].encoding == StringEncoding.SC2_BYTE_STRING


def test_memory_profile_store_records_region_hints(tmp_path: Path) -> None:
    store = MemoryProfileStore(tmp_path / "mem.db")
    session = store.start_session(pid=1234, scan_mode="full")
    store.record_handle_hit(
        session,
        handle="5-S2-1-100",
        address=0x2000,
        region_base=0x1000,
        region_size=65536,
        encoding="ascii_z",
    )
    store.record_name_binding(
        session,
        handle="5-S2-1-100",
        display_name="Nick",
        name_encoding="utf16_le_z",
        handle_address=0x2000,
        name_address=0x1F00,
    )
    store.finish_session(
        session,
        scan_mode="full",
        duration_ms=12.5,
        handles_found=1,
        names_found=1,
        regions_scanned=1,
        fallback_used=False,
    )
    hints = store.top_region_hints()
    assert hints and hints[0].region_base == 0x1000
    preview = store.preview()
    assert preview["sessions"] == 1
    assert preview["name_bindings"] == 1


def test_targeted_scan_uses_recorded_regions(tmp_path: Path) -> None:
    store = MemoryProfileStore(tmp_path / "mem.db")
    session = store.start_session(pid=1, scan_mode="full")
    store.record_handle_hit(
        session,
        handle="5-S2-1-555",
        address=0x10010,
        region_base=0x10000,
        region_size=4096,
        encoding="ascii_z",
    )
    store.finish_session(
        session,
        scan_mode="full",
        duration_ms=1,
        handles_found=1,
        names_found=0,
        regions_scanned=1,
        fallback_used=False,
    )

    class FakeHandle:
        pass

    memory = {
        0x10000: b"lobby 5-S2-1-555 5-S2-1-666 end",
    }

    def fake_iter(_handle, heap_only=False):
        return iter([(0x10000, 4096)])

    def fake_read(_handle, address, size):
        return memory.get(address, b"")

    import antismurf.lobby.lobby_handles as lh_mod
    import antismurf.lobby.memory_reader as mr

    original_iter = mr._iter_readable_regions
    original_read = mr._read_memory
    mr._iter_readable_regions = fake_iter
    mr._read_memory = fake_read
    lh_mod._read_memory = fake_read
    lh_mod._iter_readable_regions = fake_iter
    try:
        config = AppConfig(
            memory_targeted_scan_enabled=True,
            memory_targeted_min_regions=1,
            memory_targeted_min_handles=1,
            memory_full_scan_fallback=False,
            memory_handle_scan_budget_sec=2.0,
        )
        result = lh.scan_lobby_player_handles(
            FakeHandle(),
            config,
            store=store,
        )
        assert result.scan_mode == "targeted"
        assert "5-S2-1-555" in result.handles
    finally:
        mr._iter_readable_regions = original_iter
        mr._read_memory = original_read
        lh_mod._read_memory = original_read
        lh_mod._iter_readable_regions = original_iter
