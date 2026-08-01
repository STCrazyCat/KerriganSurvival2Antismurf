import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.lobby.memory_scan_strategies import (
    ComprehensiveScanStats,
    ScanStrategies,
    collect_handles_in_window,
    collect_names_in_window,
)


def test_collect_handles_ascii_exact_window() -> None:
    handle = "5-S2-1-6738824"
    needle = handle.encode("ascii") + b"\x00"
    window_base = 0x1000
    anchor = 0x1080
    rel = anchor - window_base + 32
    data = bytearray(512)
    data[rel : rel + len(needle)] = needle

    hits = collect_handles_in_window(
        bytes(data),
        window_base=window_base,
        anchor_address=anchor,
        expected_handle=handle,
        strategies=ScanStrategies(
            handle_ascii_regex=False,
            handle_profile_triplet=False,
        ),
    )
    assert hits
    assert hits[0].handle == handle
    assert hits[0].strategy == "handle_ascii_exact_window"
    assert hits[0].address == window_base + rel


def test_collect_handles_utf16_window() -> None:
    handle = "5-S2-1-6738824"
    wide = handle.encode("utf-16-le")
    window_base = 0x2000
    rel = 64
    data = bytearray(256)
    data[rel : rel + len(wide)] = wide

    hits = collect_handles_in_window(
        bytes(data),
        window_base=window_base,
        anchor_address=window_base + rel,
        expected_handle=handle,
        strategies=ScanStrategies(
            handle_ascii_exact=False,
            handle_ascii_regex=False,
            handle_profile_triplet=False,
        ),
    )
    assert len(hits) == 1
    assert hits[0].strategy == "handle_utf16_le_window"


def test_collect_names_utf16_window() -> None:
    name = "大主教阿塔尼斯"
    encoded = name.encode("utf-16-le") + b"\x00\x00"
    window_base = 0x1C1D795B000
    rel = 0x720
    data = bytearray(0x900)
    data[rel : rel + len(encoded)] = encoded

    hits = collect_names_in_window(
        bytes(data),
        window_base=window_base,
        anchor_address=window_base + rel,
        expected_name=name,
        strategies=ScanStrategies(name_utf8=False, name_sc2_byte=False),
    )
    assert hits
    assert hits[0].text == name
    assert hits[0].strategy == "name_utf16_le_window"
    assert hits[0].address == window_base + rel


def test_collect_handles_profile_triplet() -> None:
    import struct

    handle = "5-S2-1-6738824"
    window_base = 0x5000
    rel = 128
    data = bytearray(512)
    struct.pack_into("<4I", data, rel, 5, 2, 1, 6738824)

    hits = collect_handles_in_window(
        bytes(data),
        window_base=window_base,
        anchor_address=window_base + rel,
        expected_handle=handle,
        strategies=ScanStrategies(
            handle_ascii_exact=False,
            handle_ascii_regex=False,
            handle_utf16_le=False,
        ),
    )
    assert hits
    assert hits[0].strategy == "handle_profile_triplet"


def test_stats_increment_on_window_scan() -> None:
    handle = "5-S2-1-6738824"
    needle = handle.encode("ascii")
    data = needle + b"\x00" + b"\x00" * 100
    stats = ComprehensiveScanStats()

    collect_handles_in_window(
        data,
        window_base=0,
        anchor_address=0,
        expected_handle=handle,
        stats=stats,
    )
    assert stats.handle_hits.get("handle_ascii_exact_window", 0) >= 1


def test_collect_handles_without_null_terminator() -> None:
    handle = "5-S2-1-6738824"
    needle = handle.encode("ascii")
    data = b"\x00" * 20 + needle + b"EXTRA"
    hits = collect_handles_in_window(
        data,
        window_base=0,
        anchor_address=20,
        expected_handle=handle,
        strategies=ScanStrategies(
            handle_ascii_regex=False,
            handle_utf16_le=False,
            handle_profile_triplet=False,
        ),
    )
    assert hits
    assert hits[0].handle == handle


def test_verify_handle_bytes_at_accepts_embedded_ascii(monkeypatch) -> None:
    from antismurf.lobby.memory_scan_strategies import verify_handle_bytes_at

    handle = "5-S2-1-6738824"
    payload = handle.encode("ascii") + b"\x00"

    def fake_read(_process, address, size):
        return payload[:size]

    monkeypatch.setattr(
        "antismurf.lobby.memory_scan_strategies._read_memory",
        fake_read,
    )
    assert verify_handle_bytes_at(None, 0, handle, encoding="ascii_z")
