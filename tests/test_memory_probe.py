import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.lobby.memory_probe import (
    MemoryLocation,
    NameProbeResult,
    score_name_probe,
    _collect_nearby_handles,
    format_hex_dump,
)


def test_collect_nearby_handles_finds_ascii_handle() -> None:
    name_addr = 1000
    handle = b"5-S2-1-6738824\x00"
    padding = b"\x00" * 40
    window_base = 900
    rel_name = name_addr - window_base
    data = bytearray(512)
    data[rel_name : rel_name + 20] = "大主教".encode("utf-16-le") + b"\x00\x00"
    handle_at = rel_name + 80
    data[handle_at : handle_at + len(handle)] = handle
    hits = _collect_nearby_handles(bytes(data), window_base=window_base, name_address=name_addr)
    assert hits
    assert hits[0].handle == "5-S2-1-6738824"
    assert hits[0].offset_from_name == (window_base + handle_at) - name_addr


def test_score_prefers_private_heap_over_image() -> None:
    private = NameProbeResult(
        name="测试",
        name_address=0x1000,
        name_encoding="utf16_le_z",
        location=MemoryLocation(
            address=0x1000,
            region_base=0x1000,
            region_size=0x10000,
            protect=0x04,
            region_type="private",
        ),
        handles=[],
    )
    image = NameProbeResult(
        name="测试",
        name_address=0x2000,
        name_encoding="utf16_le_z",
        location=MemoryLocation(
            address=0x2000,
            region_base=0x2000,
            region_size=0x1000,
            protect=0x02,
            region_type="image",
            module_name="SC2_x64.exe",
            module_offset=0x7D17BE0,
        ),
        handles=[],
    )
    assert score_name_probe(private).lobby_score > score_name_probe(image).lobby_score


def test_score_boosts_close_handle() -> None:
    base = NameProbeResult(
        name="大主教阿塔尼斯",
        name_address=0x1C1D795B720,
        name_encoding="utf16_le_z",
        location=MemoryLocation(
            address=0x1C1D795B720,
            region_base=0x1C1D795B000,
            region_size=0x20000,
            protect=0x04,
            region_type="private",
        ),
        handles=[],
    )
    from antismurf.lobby.memory_probe import HandleNearName

    with_handle = NameProbeResult(
        name=base.name,
        name_address=base.name_address,
        name_encoding=base.name_encoding,
        location=base.location,
        handles=[
            HandleNearName(
                handle="5-S2-1-6738824",
                handle_address=base.name_address + 48,
                offset_from_name=48,
            )
        ],
    )
    assert score_name_probe(with_handle).lobby_score > score_name_probe(base).lobby_score


def test_compare_scan_and_monitor_reports_offsets() -> None:
    from antismurf.lobby.memory_probe import (
        MemoryLocation,
        MonitorSnapshot,
        PairMonitorSession,
        PairVerificationMatch,
        PairVerificationReport,
        compare_scan_and_monitor,
    )

    scan = PairVerificationReport(
        expected_handle="5-S2-1-6738824",
        expected_name="大主教阿塔尼斯",
        matches=[
            PairVerificationMatch(
                name_address=0x1C1D795B720,
                handle_address=0x1C1D795B750,
                offset_name_to_handle=48,
                lobby_score=100.0,
                confirmed=True,
                match_source="name_scan",
                location=MemoryLocation(
                    address=0x1C1D795B720,
                    region_base=0x1C1D795B000,
                    region_size=0x10000,
                    protect=0x04,
                    region_type="private",
                ),
            )
        ],
        confirmed_count=1,
    )

    class FakeMonitor:
        baseline = MonitorSnapshot(
            phase="baseline",
            timestamp=0.0,
            name_addresses=set(),
            handle_addresses=set(),
            pair_candidates=[],
        )
        in_lobby = MonitorSnapshot(
            phase="in_lobby",
            timestamp=1.0,
            name_addresses={0x1C1D795B720},
            handle_addresses={0x1C1D795B750},
            pair_candidates=[
                PairVerificationMatch(
                    name_address=0x1C1D795B728,
                    handle_address=0x1C1D795B758,
                    offset_name_to_handle=48,
                    lobby_score=90.0,
                    confirmed=True,
                    match_source="monitor_in_lobby",
                    location=MemoryLocation(
                        address=0x1C1D795B728,
                        region_base=0x1C1D795B000,
                        region_size=0x10000,
                        protect=0x04,
                        region_type="private",
                    ),
                )
            ],
        )

    lines = compare_scan_and_monitor(scan, FakeMonitor())  # type: ignore[arg-type]
    text = "\n".join(lines)
    assert "模式对比" in text
    assert "偏移对比" in text


def test_format_hex_dump_contains_address() -> None:
    data = b"5-S2-1-6738824\x00"
    text = format_hex_dump(data, 0x1C1D795B720)
    assert "1C1D795B720" in text


def test_verify_player_pair_remote_when_not_co_located(monkeypatch) -> None:
    from antismurf.lobby.memory_probe import (
        MemoryLocation,
        PairVerificationReport,
        StandaloneHit,
        _build_remote_pair,
        verify_player_pair,
    )
    from antismurf.lobby.memory_scan_strategies import DecodedHandleHit, DecodedStringHit

    name_hit = DecodedStringHit(
        address=0x1C1D795B720,
        text="大主教阿塔尼斯",
        encoding="utf16_le_z",
        strategy="name_utf16_le_raw",
    )
    handle_hit = DecodedHandleHit(
        address=0x1C1FF9E9848,
        handle="5-S2-1-6738824",
        encoding="ascii_z",
        strategy="handle_ascii_exact_raw",
        exact=True,
    )

    monkeypatch.setattr(
        "antismurf.lobby.memory_probe.scan_process_for_decoded_strings",
        lambda *args, **kwargs: [name_hit],
    )
    monkeypatch.setattr(
        "antismurf.lobby.memory_probe.scan_process_for_decoded_handles",
        lambda *args, **kwargs: [handle_hit],
    )
    monkeypatch.setattr(
        "antismurf.lobby.memory_probe._read_memory",
        lambda *args, **kwargs: b"",
    )
    monkeypatch.setattr(
        "antismurf.lobby.memory_probe.build_module_map",
        lambda pid: [],
    )
    monkeypatch.setattr(
        "antismurf.lobby.memory_probe.locate_address",
        lambda address, **kwargs: MemoryLocation(
            address=address,
            region_base=address & ~0xFFF,
            region_size=0x10000,
            protect=0x04,
            region_type="private",
        ),
    )
    monkeypatch.setattr(
        "antismurf.lobby.memory_probe.verify_name_bytes_at",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        "antismurf.lobby.memory_probe.verify_handle_bytes_at",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        "antismurf.lobby.memory_probe.scan_channel_rosters",
        lambda *args, **kwargs: [],
    )

    report = verify_player_pair(
        None,
        pid=1234,
        expected_handle="5-S2-1-6738824",
        expected_name="大主教阿塔尼斯",
    )
    assert isinstance(report, PairVerificationReport)
    assert len(report.standalone_names) == 1
    assert len(report.standalone_handles) == 1
    assert report.remote_pair_count == 1
    assert report.matches
    assert report.matches[0].match_source == "remote_heuristic"

    remote = _build_remote_pair(
        best_name=StandaloneHit(
            address=0x1C1D795B720,
            strategy="name_utf16_le_raw",
            encoding="utf16_le_z",
            location=MemoryLocation(
                address=0x1C1D795B720,
                region_base=0x1C1D795B000,
                region_size=0x10000,
                protect=0x04,
                region_type="private",
            ),
            lobby_score=40.0,
            region_type="private",
        ),
        best_handle=StandaloneHit(
            address=0x1C1FF9E9848,
            strategy="handle_ascii_exact_raw",
            encoding="ascii_z",
            location=MemoryLocation(
                address=0x1C1FF9E9848,
                region_base=0x1C1FF9E9000,
                region_size=0x10000,
                protect=0x04,
                region_type="private",
            ),
            lobby_score=55.0,
            region_type="private",
        ),
        expected_name="大主教阿塔尼斯",
        expected_handle="5-S2-1-6738824",
    )
    assert remote.offset_name_to_handle == 0x1C1FF9E9848 - 0x1C1D795B720
    assert "远程存储" in remote.score_notes[0]

