"""Detect SC2 game-lobby chat channel rosters in memory.

KS2 rooms use the same underlying chat-channel membership as public channels:
several player handles (and often names) appear together in one memory cluster
when those players are in the room channel. Static UI / friend-list copies of
a single handle do not sit in a multi-member roster blob.

Use roster co-location to filter probe candidates and score trace hits.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from antismurf.lobby.memory_formats import extract_handle_hits, scan_utf16le_null_strings
from antismurf.lobby.memory_reader import (
    _iter_readable_regions_typed,
    _read_memory,
)
from antismurf.models.player import is_valid_handle


@dataclass(frozen=True)
class ChannelRosterCluster:
    """Handles that co-occur within one channel-style memory span."""

    region_base: int
    span_start: int
    span_end: int
    members: tuple[tuple[int, str], ...]
    member_count: int
    region_type: str
    score: float
    notes: tuple[str, ...] = ()

    @property
    def handles(self) -> tuple[str, ...]:
        return tuple(sorted({handle for _addr, handle in self.members}))

    @property
    def handle_addresses(self) -> tuple[int, ...]:
        return tuple(addr for addr, _handle in self.members)

    def contains_address(self, address: int, *, slack: int = 512) -> bool:
        return (self.span_start - slack) <= address <= (self.span_end + slack)

    def contains_handle(self, handle: str) -> bool:
        return handle in self.handles

    def address_for_handle(self, handle: str) -> int | None:
        for addr, item in self.members:
            if item == handle:
                return addr
        return None

    def summary_line(self) -> str:
        handle_text = ", ".join(self.handles[:6])
        if len(self.handles) > 6:
            handle_text += f" (+{len(self.handles) - 6})"
        return (
            f"频道 roster [{self.region_type}] "
            f"0x{self.span_start:X}..0x{self.span_end:X} "
            f"{self.member_count} 人: {handle_text} (分={self.score:.0f})"
        )


@dataclass
class ChannelRosterSnapshot:
    timestamp: float
    phase: str
    clusters: list[ChannelRosterCluster] = field(default_factory=list)

    @property
    def member_handles(self) -> set[str]:
        result: set[str] = set()
        for cluster in self.clusters:
            result.update(cluster.handles)
        return result

    def clusters_for_handle(self, handle: str) -> list[ChannelRosterCluster]:
        return [cluster for cluster in self.clusters if cluster.contains_handle(handle)]

    def address_in_roster_for(self, address: int, handle: str, *, slack: int = 512) -> bool:
        for cluster in self.clusters_for_handle(handle):
            if cluster.contains_address(address, slack=slack):
                return True
        return False


def find_handle_clusters_in_data(
    data: bytes,
    *,
    window_base: int,
    region_base: int,
    region_type: str,
    min_members: int = 2,
    max_span: int = 8192,
    priority_handles: set[str] | None = None,
) -> list[ChannelRosterCluster]:
    hits = extract_handle_hits(data)
    if len(hits) < min_members:
        return []

    positions: list[tuple[int, str]] = []
    seen: set[tuple[int, str]] = set()
    for rel_offset, handle, _encoding in hits:
        if not is_valid_handle(handle):
            continue
        address = window_base + rel_offset
        key = (address, handle)
        if key in seen:
            continue
        seen.add(key)
        positions.append((address, handle))
    positions.sort(key=lambda item: item[0])

    clusters: list[ChannelRosterCluster] = []
    index = 0
    while index < len(positions):
        start_addr, _start_handle = positions[index]
        group_addrs: list[int] = [start_addr]
        group_handles: set[str] = {positions[index][1]}
        next_index = index + 1
        while next_index < len(positions):
            addr, handle = positions[next_index]
            if addr - start_addr > max_span:
                break
            group_addrs.append(addr)
            group_handles.add(handle)
            next_index += 1
        if len(group_handles) >= min_members:
            span_start = min(group_addrs)
            span_end = max(group_addrs)
            score = float(len(group_handles) * 12)
            notes: list[str] = [f"{len(group_handles)} handles in {max_span}B span"]
            if priority_handles and group_handles & priority_handles:
                score += 25.0
                notes.append("contains known room member")
            if region_type == "private":
                score += 20.0
                notes.append("private heap")
            ordered_members = tuple(
                sorted(
                    ((addr, handle) for addr, handle in positions[index:next_index]),
                    key=lambda item: item[0],
                )
            )
            group_handles = {handle for _addr, handle in ordered_members}
            clusters.append(
                ChannelRosterCluster(
                    region_base=region_base,
                    span_start=span_start,
                    span_end=span_end,
                    members=ordered_members,
                    member_count=len(group_handles),
                    region_type=region_type,
                    score=score,
                    notes=tuple(notes),
                )
            )
        index = max(index + 1, next_index)

    return _dedupe_clusters(clusters)


def _dedupe_clusters(clusters: list[ChannelRosterCluster]) -> list[ChannelRosterCluster]:
    clusters.sort(key=lambda item: (item.score, item.member_count), reverse=True)
    kept: list[ChannelRosterCluster] = []
    for cluster in clusters:
        if any(
            abs(cluster.span_start - existing.span_start) < 256
            and cluster.handles == existing.handles
            for existing in kept
        ):
            continue
        kept.append(cluster)
    return kept


def scan_channel_rosters(
    process_handle,
    *,
    known_handles: set[str] | None = None,
    min_members: int = 2,
    max_span: int = 8192,
    time_budget_sec: float = 8.0,
    prefer_private: bool = True,
    chunk_size: int = 65536,
    use_lobby_member_struct: bool = True,
    lobby_member_max_slots: int = 12,
) -> list[ChannelRosterCluster]:
    """Scan heap/mapped regions for multi-handle channel roster blobs."""
    priority = known_handles or set()
    started = time.perf_counter()
    all_clusters: list[ChannelRosterCluster] = []

    regions: list[tuple[int, int, str]] = list(
        _iter_readable_regions_typed(process_handle)
    )
    if prefer_private:
        regions.sort(
            key=lambda item: (0 if item[2] == "private" else 1, -item[0]),
        )

    budget_per_pass = time_budget_sec / 2 if use_lobby_member_struct else time_budget_sec

    for region_base, region_size, region_type in regions:
        if time.perf_counter() - started > budget_per_pass:
            break
        if prefer_private and region_type == "image":
            continue
        if region_size > 32 * 1024 * 1024:
            region_size = 32 * 1024 * 1024
        offset = 0
        while offset < region_size:
            if time.perf_counter() - started > budget_per_pass:
                break
            read_size = min(chunk_size, region_size - offset)
            data = _read_memory(process_handle, region_base + offset, read_size)
            if not data:
                offset += read_size
                continue
            all_clusters.extend(
                find_handle_clusters_in_data(
                    data,
                    window_base=region_base + offset,
                    region_base=region_base,
                    region_type=region_type,
                    min_members=min_members,
                    max_span=max_span,
                    priority_handles=priority,
                )
            )
            offset += read_size

    if use_lobby_member_struct:
        from antismurf.lobby.memory_lobby_roster import scan_lobby_struct_rosters

        struct_started = time.perf_counter()
        struct_budget = max(2.0, time_budget_sec - (struct_started - started))
        all_clusters.extend(
            scan_lobby_struct_rosters(
                process_handle,
                known_handles=priority,
                min_members=min_members,
                max_members=lobby_member_max_slots,
                time_budget_sec=struct_budget,
                prefer_private=prefer_private,
                chunk_size=chunk_size,
            )
        )

    return _dedupe_clusters(all_clusters)


def roster_delta(
    current: ChannelRosterSnapshot,
    baseline: ChannelRosterSnapshot | None,
) -> tuple[list[ChannelRosterCluster], set[str]]:
    """Clusters and handles present now but not in baseline (joined channel)."""
    if baseline is None:
        return list(current.clusters), set(current.member_handles)
    baseline_keys = {
        (cluster.span_start, cluster.handles) for cluster in baseline.clusters
    }
    new_clusters = [
        cluster
        for cluster in current.clusters
        if (cluster.span_start, cluster.handles) not in baseline_keys
    ]
    new_handles = current.member_handles - baseline.member_handles
    return new_clusters, new_handles


def pick_name_in_roster_window(
    process_handle,
    cluster: ChannelRosterCluster,
    display_name: str,
    *,
    slack: int = 1024,
) -> int | None:
    """Find nickname inside a roster span (struct UTF-8 row or UTF-16 scan)."""
    from antismurf.lobby.memory_lobby_roster import pick_struct_name_address

    struct_addr = pick_struct_name_address(process_handle, cluster, display_name)
    if struct_addr is not None:
        return struct_addr

    start = max(0, cluster.span_start - slack)
    end = cluster.span_end + slack
    size = end - start
    if size <= 0 or size > 64 * 1024:
        return None
    data = _read_memory(process_handle, start, size) or b""
    needle = display_name.encode("utf-16-le")
    rel = data.find(needle)
    if rel < 0:
        for decoded in scan_utf16le_null_strings(data):
            if decoded.text.strip() == display_name.strip():
                return start + decoded.offset
        return None
    return start + rel


def pick_handle_address_in_cluster(
    cluster: ChannelRosterCluster,
    handle: str,
) -> int | None:
    return cluster.address_for_handle(handle)
