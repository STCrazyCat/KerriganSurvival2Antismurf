import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.data.player_display import sighting_snapshot_from_record
from antismurf.models.community import CommunityRating
from antismurf.models.evaluation import PlayerRecord
from antismurf.storage.store import PlayerStore


def test_upsert_player_sighting_keeps_first_seen(tmp_path: Path) -> None:
    async def run() -> None:
        store = PlayerStore(tmp_path / "test.db")
        await store.init()

        record = PlayerRecord(
            handle="5-S2-1-1000",
            slot_index=2,
            display_name="Tester",
            team_name="TeamA",
            tier="high",
            score=65.0,
            triggered_rules=["playlike_top3_lift_800"],
            community=CommunityRating(handle="5-S2-1-1000", mmr=1500, mmr_playlike=2400),
        )
        await store.upsert_player_sighting(record)
        record.score = 80.0
        record.tier = "critical"
        await store.upsert_player_sighting(record)

        entries = await store.list_player_sightings()
        assert len(entries) == 1
        entry = entries[0]
        assert entry.handle == "5-S2-1-1000"
        assert entry.display_name == "Tester"
        assert entry.team_name == "TeamA"
        assert entry.score == 80.0
        assert entry.tier == "critical"
        assert entry.seen_count == 2
        assert entry.first_seen_at <= entry.last_seen_at
        assert entry.snapshot.get("handle") == "5-S2-1-1000"
        assert "survivor_mmr" in entry.snapshot

    asyncio.run(run())


def test_list_player_sightings_orders_by_last_seen(tmp_path: Path) -> None:
    async def run() -> None:
        store = PlayerStore(tmp_path / "test.db")
        await store.init()

        older = PlayerRecord(
            handle="5-S2-1-1",
            slot_index=0,
            display_name="Old",
            updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        newer = PlayerRecord(
            handle="5-S2-1-2",
            slot_index=1,
            display_name="New",
            updated_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
        await store.upsert_player_sighting(older)
        await asyncio.sleep(0.01)
        await store.upsert_player_sighting(newer)

        handles = [item.handle for item in await store.list_player_sightings()]
        assert handles[0] == "5-S2-1-2"

    asyncio.run(run())


def test_sighting_snapshot_from_record_includes_faction_blocks() -> None:
    record = PlayerRecord(
        handle="5-S2-1-1000",
        slot_index=0,
        display_name="Nick",
        tier="medium",
        score=25.0,
        community=CommunityRating(handle="5-S2-1-1000", mmr=1600, mmr_playlike=2100),
    )
    snap = sighting_snapshot_from_record(record)
    assert snap["display_name"] == "Nick"
    assert snap["handle"] == "5-S2-1-1000"
    assert "survivor_mmr" in snap
    assert "kerrigan_pl" in snap
