from __future__ import annotations

import ctypes
import logging
import time
from collections.abc import Callable, Iterator
from ctypes import wintypes

from antismurf.lobby.memory_formats import (
    StringEncoding,
    extract_handle_hits,
    scan_utf16le_null_strings,
)

logger = logging.getLogger(__name__)

MEM_COMMIT = 0x1000
PAGE_NOACCESS = 0x01
PAGE_GUARD = 0x100

READABLE_PROTECT = {
    0x02,  # PAGE_READONLY
    0x04,  # PAGE_READWRITE
    0x08,  # PAGE_WRITECOPY
    0x20,  # PAGE_EXECUTE_READ
    0x40,  # PAGE_EXECUTE_READWRITE
    0x80,  # PAGE_EXECUTE_WRITECOPY
}

MEM_PRIVATE = 0x20000
MEM_MAPPED = 0x40000
MEM_IMAGE = 0x1000000

REGION_TYPE_LABELS = {
    MEM_PRIVATE: "private",
    MEM_MAPPED: "mapped",
    MEM_IMAGE: "image",
}


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_void_p),
        ("AllocationBase", ctypes.c_void_p),
        ("AllocationProtect", wintypes.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    ]


def _iter_readable_regions(
    process_handle,
    *,
    heap_only: bool = False,
) -> Iterator[tuple[int, int]]:
    for base, size, _region_type in _iter_readable_regions_typed(
        process_handle,
        heap_only=heap_only,
    ):
        yield base, size


def _iter_readable_regions_typed(
    process_handle,
    *,
    heap_only: bool = False,
) -> Iterator[tuple[int, int, str]]:
    import sys

    kernel32 = ctypes.windll.kernel32
    mbi = MEMORY_BASIC_INFORMATION()
    address = 0
    max_address = (1 << 63) - 1 if sys.maxsize > 2**32 else 0x7FFFFFFF0000

    while address < max_address:
        result = kernel32.VirtualQueryEx(
            process_handle,
            ctypes.c_void_p(address),
            ctypes.byref(mbi),
            ctypes.sizeof(mbi),
        )
        if result == 0:
            break
        base = int(ctypes.cast(mbi.BaseAddress, ctypes.c_void_p).value or 0)
        size = int(mbi.RegionSize)
        if size <= 0:
            break
        protect = int(mbi.Protect)
        state = int(mbi.State)
        if (
            state == MEM_COMMIT
            and protect in READABLE_PROTECT
            and protect not in (PAGE_GUARD, PAGE_NOACCESS)
        ):
            region_type = REGION_TYPE_LABELS.get(int(mbi.Type), f"type_{int(mbi.Type)}")
            if not heap_only or _looks_like_heap_region(base, size):
                yield base, size, region_type
        address = base + size


def iter_readable_regions_heap_first(process_handle) -> Iterator[tuple[int, int]]:
    """Yield readable regions with private heap first (high addresses first)."""
    private: list[tuple[int, int]] = []
    other: list[tuple[int, int]] = []
    for base, size, region_type in _iter_readable_regions_typed(process_handle):
        if region_type == "private":
            private.append((base, size))
        else:
            other.append((base, size))
    private.sort(key=lambda item: item[0], reverse=True)
    for base, size in private + other:
        yield base, size


def _looks_like_heap_region(base: int, size: int) -> bool:
    if size < 64 * 1024:
        return False
    if size > 512 * 1024 * 1024:
        return False
    return True


def _read_memory(process_handle, address: int, size: int) -> bytes | None:
    kernel32 = ctypes.windll.kernel32
    buffer = ctypes.create_string_buffer(size)
    bytes_read = ctypes.c_size_t(0)
    ok = kernel32.ReadProcessMemory(
        process_handle,
        ctypes.c_void_p(address),
        buffer,
        size,
        ctypes.byref(bytes_read),
    )
    if not ok or bytes_read.value <= 0:
        return None
    return buffer.raw[: bytes_read.value]


def extract_ascii_handles(data: bytes) -> list[tuple[int, str]]:
    return [
        (offset, handle)
        for offset, handle, _encoding in extract_handle_hits(data)
    ]


def extract_utf16_handles(data: bytes) -> list[tuple[int, str]]:
    """Legacy helper — handles in SC2 are ASCII; UTF-16-wide handles are rare."""
    results: list[tuple[int, str]] = []
    for decoded in scan_utf16le_null_strings(data, max_chars=64):
        from antismurf.models.player import extract_handle_from_text, is_valid_handle

        handle = extract_handle_from_text(decoded.text)
        if handle and is_valid_handle(handle):
            results.append((decoded.offset, handle))
    return results


def scan_process_memory(
    process_handle,
    needle: bytes,
    *,
    chunk_size: int = 65536,
    time_budget_sec: float = 2.0,
    region_filter: Callable[[int, int], bool] | None = None,
    reverse: bool = False,
) -> list[int]:
    """Return virtual addresses where ``needle`` appears."""
    hits: list[int] = []
    started = time.perf_counter()
    regions = list(_iter_readable_regions(process_handle, heap_only=False))
    if reverse:
        regions.reverse()
    for base, size in regions:
        if time.perf_counter() - started > time_budget_sec:
            break
        if region_filter is not None and not region_filter(base):
            continue
        offset = 0
        while offset < size:
            if time.perf_counter() - started > time_budget_sec:
                break
            read_size = min(chunk_size, size - offset)
            data = _read_memory(process_handle, base + offset, read_size)
            if not data:
                offset += read_size
                continue
            pos = 0
            while True:
                found = data.find(needle, pos)
                if found < 0:
                    break
                hits.append(base + offset + found)
                pos = found + 1
            offset += read_size
    return hits


def detect_local_handle(
    process_handle,
    *,
    pid: int | None = None,
    time_budget_sec: float = 2.0,
    chunk_size: int = 65536,
    use_host_anchor: bool = True,
    host_anchor_offset: int = 0x3E2F340,
) -> str | None:
    """Infer the local account handle (module anchor first, then Accounts path)."""
    if use_host_anchor and pid is not None:
        from antismurf.lobby.memory_host_anchor import detect_host_handle

        anchored = detect_host_handle(
            process_handle,
            pid=pid,
            offset=host_anchor_offset,
        )
        if anchored:
            return anchored

    marker = "StarCraft II\\Accounts".encode("utf-16-le")
    addresses = scan_process_memory(
        process_handle,
        marker,
        chunk_size=chunk_size,
        time_budget_sec=time_budget_sec,
    )
    for address in addresses[:8]:
        data = _read_memory(process_handle, max(0, address - 256), 1024)
        if not data:
            continue
        for _offset, handle, _encoding in extract_handle_hits(data):
            return handle
    return None
