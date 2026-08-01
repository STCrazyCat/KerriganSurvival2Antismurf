import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.lobby.memory_channel_roster import (
    ChannelRosterCluster,
    find_handle_clusters_in_data,
    roster_delta,
    ChannelRosterSnapshot,
)


def test_find_handle_clusters_groups_nearby_handles() -> None:
    h1 = b"5-S2-1-6738824\x00"
    h2 = b"5-S2-1-12208616\x00"
    data = bytearray(512)
    data[64 : 64 + len(h1)] = h1
    data[192 : 192 + len(h2)] = h2
    clusters = find_handle_clusters_in_data(
        bytes(data),
        window_base=0x1000,
        region_base=0x1000,
        region_type="private",
        min_members=2,
        max_span=512,
        priority_handles={"5-S2-1-6738824", "5-S2-1-12208616"},
    )
    assert len(clusters) == 1
    assert clusters[0].member_count == 2
    assert clusters[0].contains_handle("5-S2-1-6738824")
    assert clusters[0].contains_handle("5-S2-1-12208616")


def test_roster_delta_finds_new_channel_members() -> None:
    baseline = ChannelRosterSnapshot(
        timestamp=0.0,
        phase="out_room",
        clusters=[
            ChannelRosterCluster(
                region_base=0x1000,
                span_start=0x1100,
                span_end=0x1200,
                members=((0x1100, "5-S2-1-1111111"),),
                member_count=1,
                region_type="private",
                score=10.0,
            )
        ],
    )
    current = ChannelRosterSnapshot(
        timestamp=1.0,
        phase="in_room",
        clusters=[
            ChannelRosterCluster(
                region_base=0x2000,
                span_start=0x2100,
                span_end=0x2300,
                members=(
                    (0x2100, "5-S2-1-6738824"),
                    (0x2200, "5-S2-1-12208616"),
                ),
                member_count=2,
                region_type="private",
                score=40.0,
            )
        ],
    )
    new_clusters, new_handles = roster_delta(current, baseline)
    assert len(new_clusters) == 1
    assert "5-S2-1-6738824" in new_handles


def test_cluster_address_for_handle() -> None:
    cluster = ChannelRosterCluster(
        region_base=0x1000,
        span_start=0x1100,
        span_end=0x1200,
        members=((0x1150, "5-S2-1-6738824"),),
        member_count=1,
        region_type="private",
        score=1.0,
    )
    assert cluster.address_for_handle("5-S2-1-6738824") == 0x1150
    assert cluster.contains_address(0x1150)
