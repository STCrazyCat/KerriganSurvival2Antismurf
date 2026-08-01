import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.lobby.memory_host_anchor import (
    DEFAULT_HOST_HANDLE_MODULE_OFFSET,
    anchor_proximity_bonus,
    read_host_handle_anchor,
    scan_module_vicinity_handles,
)
from antismurf.lobby.memory_probe import ModuleInfo


class FakeHandle:
    pass


def _make_modules(base: int = 0x7FF600000000, size: int = 0x5000000) -> list[ModuleInfo]:
    return [ModuleInfo(name="SC2_x64.exe", base=base, size=size)]


def test_read_host_handle_anchor_ascii_at_offset() -> None:
    handle = "5-S2-1-12208616"
    modules = _make_modules()
    anchor_address = modules[0].base + DEFAULT_HOST_HANDLE_MODULE_OFFSET
    read_start = anchor_address - 64
    memory = {read_start: b"\x00" * 64 + handle.encode("ascii") + b"\x00"}

    import antismurf.lobby.memory_host_anchor as ha

    original = ha._read_memory

    def fake_read(_handle, address, size):
        chunk = memory.get(address, b"")
        if chunk:
            return chunk[:size]
        for base, data in memory.items():
            if base <= address < base + len(data):
                rel = address - base
                return data[rel : rel + size]
        return b""

    ha._read_memory = fake_read
    try:
        anchor = read_host_handle_anchor(FakeHandle(), modules)
        assert anchor is not None
        assert anchor.handle == handle
        assert anchor.handle_address == anchor_address
        assert anchor.encoding == "ascii_z"
        assert anchor.module_label == f"SC2_x64.exe+0x{DEFAULT_HOST_HANDLE_MODULE_OFFSET:X}"
    finally:
        ha._read_memory = original


def test_read_host_handle_anchor_profile_triplet() -> None:
    handle = "5-S2-1-12208616"
    modules = _make_modules()
    anchor_address = modules[0].base + DEFAULT_HOST_HANDLE_MODULE_OFFSET
    read_start = anchor_address - 64
    triplet = struct.pack("<4I", 5, 2, 1, 12208616)
    memory = {read_start: b"\x00" * 64 + triplet}

    import antismurf.lobby.memory_host_anchor as ha

    original = ha._read_memory

    def fake_read(_handle, address, size):
        for base, data in memory.items():
            if base <= address < base + len(data):
                rel = address - base
                return data[rel : rel + size]
        return b""

    ha._read_memory = fake_read
    try:
        anchor = read_host_handle_anchor(FakeHandle(), modules)
        assert anchor is not None
        assert anchor.handle == handle
        assert anchor.encoding == "profile_triplet"
    finally:
        ha._read_memory = original


def test_scan_module_vicinity_handles() -> None:
    host = "5-S2-1-1111111"
    guest = "5-S2-1-2222222"
    modules = _make_modules()
    anchor_address = modules[0].base + DEFAULT_HOST_HANDLE_MODULE_OFFSET
    radius = 256
    block_start = anchor_address - radius
    block = (
        b"\x00" * radius
        + host.encode("ascii")
        + b"\x00padding"
        + guest.encode("ascii")
        + b"\x00"
    )
    memory = {block_start: block}

    import antismurf.lobby.memory_host_anchor as ha

    original = ha._read_memory

    def fake_read(_handle, address, size):
        for base, data in memory.items():
            if base <= address < base + len(data):
                rel = address - base
                return data[rel : rel + size]
        return b""

    ha._read_memory = fake_read
    try:
        anchor = read_host_handle_anchor(FakeHandle(), modules)
        assert anchor is not None
        hits = scan_module_vicinity_handles(
            FakeHandle(),
            anchor,
            modules,
            radius=radius,
        )
        handles = {item.handle for item in hits}
        assert host in handles
        assert guest in handles
    finally:
        ha._read_memory = original


def test_anchor_proximity_bonus() -> None:
    modules = _make_modules()
    anchor_address = modules[0].base + DEFAULT_HOST_HANDLE_MODULE_OFFSET

    from antismurf.lobby.memory_host_anchor import HostHandleAnchor

    anchor_obj = HostHandleAnchor(
        module_name="SC2_x64.exe",
        module_base=modules[0].base,
        anchor_offset=DEFAULT_HOST_HANDLE_MODULE_OFFSET,
        anchor_address=anchor_address,
        handle="5-S2-1-1",
        handle_address=anchor_address,
        encoding="ascii_z",
        module_label="SC2_x64.exe+0x3E2F340",
    )
    exact_bonus, _notes = anchor_proximity_bonus(anchor_address, anchor_obj)
    assert exact_bonus >= 75.0
    far_bonus, _ = anchor_proximity_bonus(anchor_address + 100_000, anchor_obj)
    assert far_bonus == 0.0
