import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.lobby.memory_trace_session import (
    TraceCandidate,
    compute_confirm_score,
    infer_struct_bases,
    is_confirmed_candidate,
    trace_pointer_roots_iterative,
    _find_pointers_in_window,
)


def test_confirmed_candidate_requires_enter_leave_toggle() -> None:
    static = TraceCandidate(
        kind="name",
        address=0x1000,
        region_type="image",
        module_label="SC2_x64.exe+0x1",
        lobby_score=10.0,
        seen_in_room=3,
        seen_out_room=3,
        present_after_enter=0,
        absent_after_leave=0,
    )
    assert not is_confirmed_candidate(static)

    live = TraceCandidate(
        kind="handle",
        address=0x1C1FF9E9848,
        region_type="private",
        module_label="0x1C1FF9E9848",
        lobby_score=40.0,
        seen_in_room=2,
        seen_out_room=1,
        present_after_enter=2,
        absent_after_leave=1,
        write_events=1,
    )
    assert is_confirmed_candidate(live)
    assert live.confirm_score >= 45.0


def test_compute_confirm_score_penalizes_static_image() -> None:
    image = TraceCandidate(
        kind="name",
        address=0x7D17BE0,
        region_type="image",
        module_label="SC2_x64.exe+0x7D17BE0",
        lobby_score=5.0,
        seen_in_room=2,
        seen_out_room=2,
        present_after_enter=0,
        absent_after_leave=0,
    )
    private = TraceCandidate(
        kind="name",
        address=0x1C1D795B720,
        region_type="private",
        module_label="0x1C1D795B720",
        lobby_score=40.0,
        seen_in_room=2,
        seen_out_room=1,
        present_after_enter=2,
        absent_after_leave=1,
        write_events=2,
    )
    assert compute_confirm_score(private) > compute_confirm_score(image)


def test_infer_struct_bases_remote_layout() -> None:
    name_addr = 0x1C1D795B720
    handle_addr = 0x1C1FF9E9848
    bases = infer_struct_bases(
        [name_addr],
        [handle_addr],
        region_types={name_addr: "private", handle_addr: "private"},
    )
    assert bases
    name_bases = [b for b in bases if b.name_offset is not None]
    handle_bases = [b for b in bases if b.handle_offset is not None]
    assert name_bases
    assert handle_bases


def test_find_pointers_in_window() -> None:
    import struct

    target = 0x1C1D795B750
    ref_offset = 0x20
    data = bytearray(0x80)
    struct.pack_into("<Q", data, ref_offset, target)
    refs = _find_pointers_in_window(bytes(data), 0x1C1D795B700, target)
    assert 0x1C1D795B720 in refs


def test_trace_pointer_roots_avoids_cycle(monkeypatch) -> None:
    import struct

    field = 0x2000
    blob = bytearray(0x1200)
    struct.pack_into("<Q", blob, 0x800, field)

    def fake_read(_proc, address, size):
        start = address - 0x1000
        if start < 0:
            return b""
        return bytes(blob[start : start + size])

    def fake_locate(address, **kwargs):
        from antismurf.lobby.memory_probe import MemoryLocation

        return MemoryLocation(
            address=address,
            region_base=0x1000,
            region_size=0x2000,
            protect=0x04,
            region_type="private",
        )

    monkeypatch.setattr(
        "antismurf.lobby.memory_trace_session._read_memory",
        fake_read,
    )
    monkeypatch.setattr(
        "antismurf.lobby.memory_trace_session.locate_address",
        fake_locate,
    )

    chains = trace_pointer_roots_iterative(
        None,
        field,
        [],
        max_depth=4,
        max_chains=8,
        search_back_bytes=0x1000,
    )
    for chain in chains:
        assert len(set(chain.chain)) == len(chain.chain)
