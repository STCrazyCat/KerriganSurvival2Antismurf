import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.lobby import lobby_handles as lh
from antismurf.lobby.lobby_names import (
    attach_display_names,
    is_memory_display_name,
)
from antismurf.lobby.memory_reader import (
    extract_ascii_handles,
    extract_utf16_handles,
    scan_process_memory,
)


def test_extract_ascii_handles() -> None:
    data = b"prefix 5-S2-1-1234567 suffix"
    hits = extract_ascii_handles(data)
    assert hits == [(7, "5-S2-1-1234567")]


def test_extract_utf16_handles() -> None:
    text = "player 5-S2-1-7654321 end"
    data = text.encode("utf-16-le")
    hits = extract_utf16_handles(data)
    assert any(handle == "5-S2-1-7654321" for _, handle in hits)


def test_extract_ignores_invalid_tokens() -> None:
    data = b"not-a-handle"
    assert extract_ascii_handles(data) == []


def test_is_memory_display_name() -> None:
    assert is_memory_display_name("星际战士")
    assert is_memory_display_name("<#战队>#12345")
    assert not is_memory_display_name("5-S2-1-123")
    assert not is_memory_display_name("a")


def test_select_lobby_handles_excludes_host() -> None:
    hits = [
        lh.HandleHit("5-S2-1-111", 100, "ascii"),
        lh.HandleHit("5-S2-1-222", 200, "utf16"),
        lh.HandleHit("5-S2-1-222", 300, "utf16"),
    ]
    handles = lh.select_lobby_handles(
        hits,
        exclude_handles=frozenset({"5-S2-1-111"}),
    )
    assert handles == ["5-S2-1-222"]


def test_scan_process_memory_with_mock() -> None:
    class FakeHandle:
        pass

    regions = [(0x1000, 32)]
    memory = {
        0x1000: b"hello 5-S2-1-9999999 world",
    }

    def fake_iter(_handle, heap_only=False):
        return iter(regions)

    def fake_read(_handle, address, size):
        return memory.get(address, b"")

    import antismurf.lobby.memory_reader as mr

    original_iter = mr._iter_readable_regions
    original_read = mr._read_memory
    mr._iter_readable_regions = fake_iter
    mr._read_memory = fake_read
    try:
        hits = scan_process_memory(
            FakeHandle(),
            b"5-S2-1-9999999",
            chunk_size=64,
            time_budget_sec=1.0,
        )
        assert hits == [0x1000 + 6]
    finally:
        mr._iter_readable_regions = original_iter
        mr._read_memory = original_read


def test_attach_display_names_from_nearby_utf16() -> None:
    handle = "5-S2-1-4242424"
    name = "NickName"
    padding = b"\x00" * 40
    block = padding + name.encode("utf-16-le") + b"\x00\x00" + handle.encode("ascii")
    hit_address = 40 + len(name.encode("utf-16-le")) + 2

    class FakeHandle:
        pass

    import antismurf.lobby.lobby_names as ln

    original_read = ln._read_memory

    def fake_read(_handle, address, size):
        start = max(0, address)
        end = min(len(block), start + size)
        return block[start:end]

    ln._read_memory = fake_read
    try:
        from antismurf.config.settings import AppConfig

        config = AppConfig(memory_name_search_radius=128)
        hits = [lh.HandleHit(handle, hit_address, "ascii")]
        names = attach_display_names(FakeHandle(), hits, [handle], config)
        assert names.get(handle) == name
    finally:
        ln._read_memory = original_read


def test_memory_lobby_reader_disabled() -> None:
    from antismurf.config.settings import AppConfig
    from antismurf.lobby.memory_lobby_reader import MemoryLobbyReader

    reader = MemoryLobbyReader(AppConfig(memory_enabled=False))
    snapshot = reader.read_lobby_snapshot()
    assert snapshot.error == "Memory scan disabled"
    assert snapshot.handles == []
