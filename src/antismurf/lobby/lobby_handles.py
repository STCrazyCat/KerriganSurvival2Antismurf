from __future__ import annotations

import logging
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

from antismurf.config.settings import AppConfig
from antismurf.lobby.memory_formats import StringEncoding, extract_handle_hits
from antismurf.lobby.memory_profile_store import MemoryProfileStore
from antismurf.lobby.memory_reader import (
    _iter_readable_regions,
    _read_memory,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HandleHit:
    handle: str
    address: int
    encoding: str
    region_base: int = 0
    region_size: int = 0


@dataclass
class HandleScanResult:
    handles: list[str]
    hits: list[HandleHit]
    scan_mode: str
    regions_scanned: int = 0
    fallback_used: bool = False
    duration_ms: float = 0.0


def collect_handle_hits_in_regions(
    process_handle,
    regions: list[tuple[int, int]],
    config: AppConfig,
    *,
    time_budget_sec: float,
) -> tuple[list[HandleHit], int]:
    chunk_size = config.memory_chunk_size
    started = time.perf_counter()
    hits: list[HandleHit] = []
    scanned = 0

    for base, size in regions:
        if time.perf_counter() - started > time_budget_sec:
            break
        scanned += 1
        offset = 0
        while offset < size:
            if time.perf_counter() - started > time_budget_sec:
                break
            read_size = min(chunk_size, size - offset)
            data = _read_memory(process_handle, base + offset, read_size)
            if not data:
                offset += read_size
                continue
            for rel_offset, handle, encoding in extract_handle_hits(data):
                hits.append(
                    HandleHit(
                        handle=handle,
                        address=base + offset + rel_offset,
                        encoding=encoding.value,
                        region_base=base,
                        region_size=size,
                    )
                )
            offset += read_size
    return hits, scanned


def collect_handle_hits(
    process_handle,
    config: AppConfig,
    *,
    time_budget_sec: float | None = None,
    region_filter: Callable[[int, int], bool] | None = None,
    reverse: bool = False,
    regions: list[tuple[int, int]] | None = None,
) -> tuple[list[HandleHit], int]:
    budget = time_budget_sec or config.memory_handle_scan_budget_sec
    if regions is None:
        regions = list(_iter_readable_regions(process_handle, heap_only=False))
        if region_filter is not None:
            regions = [item for item in regions if region_filter(*item)]
        if reverse:
            regions.reverse()
    hits, scanned = collect_handle_hits_in_regions(
        process_handle,
        regions,
        config,
        time_budget_sec=budget,
    )
    return hits, scanned


def lobby_region_filter(_base: int, size: int) -> bool:
    return 256 * 1024 <= size <= 256 * 1024 * 1024


def select_lobby_handles(
    hits: list[HandleHit],
    *,
    exclude_handles: frozenset[str] | set[str] | None = None,
    min_occurrences: int = 1,
) -> list[str]:
    excluded = exclude_handles or frozenset()
    counts = Counter(hit.handle for hit in hits if hit.handle not in excluded)
    ordered: list[str] = []
    seen: set[str] = set()
    for hit in hits:
        if hit.handle in excluded or hit.handle in seen:
            continue
        if counts[hit.handle] < min_occurrences:
            continue
        ordered.append(hit.handle)
        seen.add(hit.handle)
    return ordered


def _sort_handles_by_address(handles: list[str], hits: list[HandleHit]) -> list[str]:
    first_address: dict[str, int] = {}
    for hit in hits:
        if hit.handle not in first_address:
            first_address[hit.handle] = hit.address
    return sorted(handles, key=lambda handle: first_address.get(handle, 0))


def _live_regions_map(process_handle) -> dict[int, int]:
    try:
        return {
            base: size
            for base, size in _iter_readable_regions(process_handle, heap_only=False)
        }
    except (OSError, ValueError, TypeError, Exception):
        return {}


def _regions_from_hints(
    process_handle,
    store: MemoryProfileStore,
    *,
    limit: int,
) -> list[tuple[int, int]]:
    hints = store.top_region_hints(limit)
    if not hints:
        return []
    live_regions = _live_regions_map(process_handle)
    regions: list[tuple[int, int]] = []
    for hint in hints:
        size = live_regions.get(hint.region_base, hint.region_size)
        regions.append((hint.region_base, size))
    return regions


def scan_lobby_player_handles(
    process_handle,
    config: AppConfig,
    *,
    exclude_handles: frozenset[str] | set[str] | None = None,
    store: MemoryProfileStore | None = None,
) -> HandleScanResult:
    started = time.perf_counter()
    budget = config.memory_handle_scan_budget_sec
    profile_store = store or MemoryProfileStore()
    hits: list[HandleHit] = []
    regions_scanned = 0
    scan_mode = "full"
    fallback_used = False

    if config.memory_targeted_scan_enabled:
        hinted = _regions_from_hints(
            process_handle,
            profile_store,
            limit=config.memory_targeted_region_limit,
        )
        if len(hinted) >= config.memory_targeted_min_regions:
            scan_mode = "targeted"
            targeted_budget = min(budget * 0.6, 4.0)
            targeted_hits, regions_scanned = collect_handle_hits_in_regions(
                process_handle,
                hinted,
                config,
                time_budget_sec=targeted_budget,
            )
            hits.extend(targeted_hits)
            handles = select_lobby_handles(
                hits,
                exclude_handles=exclude_handles,
            )
            if len(handles) >= config.memory_targeted_min_handles:
                return HandleScanResult(
                    handles=_sort_handles_by_address(handles, hits),
                    hits=hits,
                    scan_mode=scan_mode,
                    regions_scanned=regions_scanned,
                    fallback_used=False,
                    duration_ms=(time.perf_counter() - started) * 1000,
                )
            fallback_used = True
            logger.debug(
                "Targeted memory scan found %s handles; falling back to limited full scan",
                len(handles),
            )

    if config.memory_full_scan_fallback or not config.memory_targeted_scan_enabled:
        remaining = max(budget * 0.5, 2.0)
        lobby_budget = min(remaining * 0.4, 4.0)
        heap_budget = max(remaining - lobby_budget, 2.0)

        lobby_hits, lobby_regions = collect_handle_hits(
            process_handle,
            config,
            time_budget_sec=lobby_budget,
            region_filter=lobby_region_filter,
            reverse=False,
        )
        hits.extend(lobby_hits)
        regions_scanned += lobby_regions

        heap_hits, heap_regions = collect_handle_hits(
            process_handle,
            config,
            time_budget_sec=heap_budget,
            region_filter=None,
            reverse=True,
        )
        hits.extend(heap_hits)
        regions_scanned += heap_regions
        if scan_mode == "targeted":
            scan_mode = "targeted+full"

    handles = select_lobby_handles(hits, exclude_handles=exclude_handles)
    return HandleScanResult(
        handles=_sort_handles_by_address(handles, hits),
        hits=hits,
        scan_mode=scan_mode,
        regions_scanned=regions_scanned,
        fallback_used=fallback_used,
        duration_ms=(time.perf_counter() - started) * 1000,
    )


def persist_scan_observations(
    store: MemoryProfileStore,
    session_id: int,
    result: HandleScanResult,
) -> None:
    for hit in result.hits:
        store.record_handle_hit(
            session_id,
            handle=hit.handle,
            address=hit.address,
            region_base=hit.region_base,
            region_size=hit.region_size,
            encoding=hit.encoding,
        )
