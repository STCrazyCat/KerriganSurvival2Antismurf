import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.app.orchestrator import Orchestrator
from antismurf.config.settings import AppConfig, load_config
from antismurf.models.evaluation import PlayerRecord
from antismurf.models.player import PlayerHandle


def _record(handle: str, slot_index: int = 0) -> PlayerRecord:
    return PlayerRecord(
        handle=handle,
        slot_index=slot_index,
        discriminator=1,
        tier="medium",
        score=50,
        first_seen_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def test_remove_departed_players_by_left_list() -> None:
    orch = Orchestrator(AppConfig())
    orch._players["5-S2-1-100"] = _record("5-S2-1-100")
    orch._players["5-S2-1-200"] = _record("5-S2-1-200", slot_index=1)
    orch._notified_handles.add("5-S2-1-100")

    slots = [
        PlayerHandle(
            handle="5-S2-1-200",
            slot_index=1,
            display_text="5-S2-1-200",
            discriminator=200,
            server_id=5,
            realm_id=1,
        )
    ]
    orch._remove_departed_players(slots, left=["5-S2-1-100"])

    assert "5-S2-1-100" not in orch._players
    assert "5-S2-1-200" in orch._players
    assert "5-S2-1-100" not in orch._notified_handles


def test_remove_departed_players_on_slot_swap() -> None:
    orch = Orchestrator(AppConfig())
    orch._players["5-S2-1-1"] = _record("5-S2-1-1", slot_index=0)
    orch._notified_handles.add("5-S2-1-1")

    slots = [
        PlayerHandle(
            handle="5-S2-1-2",
            slot_index=0,
            display_text="5-S2-1-2",
            discriminator=2,
            server_id=5,
            realm_id=1,
        )
    ]
    orch._remove_departed_players(slots, left=[])

    assert "5-S2-1-1" not in orch._players
    assert "5-S2-1-2" not in orch._players


def test_remove_departed_players_updates_slot_index() -> None:
    orch = Orchestrator(AppConfig())
    orch._players["5-S2-1-1"] = _record("5-S2-1-1", slot_index=0)

    slots = [
        PlayerHandle(
            handle="5-S2-1-1",
            slot_index=3,
            display_text="5-S2-1-1",
            discriminator=1,
            server_id=5,
            realm_id=1,
        )
    ]
    orch._remove_departed_players(slots, left=[])

    assert orch._players["5-S2-1-1"].slot_index == 3


def test_kick_player_blocked_when_not_local_host() -> None:
    orch = Orchestrator(AppConfig())
    orch._is_local_host = False
    orch._players["5-S2-1-100"] = _record("5-S2-1-100")
    assert orch.kick_player("5-S2-1-100") is False


def test_set_sc2_target_pid_resets_memory_session() -> None:
    orch = Orchestrator(AppConfig(memory_enabled=True, memory_target_pid=111))
    reader = orch._memory_reader
    assert reader is not None
    reader._last_pid = 111
    reader._roster_state.record_base = 0xABC
    orch._last_lobby_snapshot = object()
    orch._last_roster_status = {"phase": "in_room"}

    orch.set_sc2_target_pid(222)

    assert orch.config.memory_target_pid == 222
    assert reader._last_pid is None
    assert reader._roster_state.record_base is None
    assert orch._last_lobby_snapshot is None
    assert orch._last_roster_status == {}


def test_roster_list_only_syncs_players_without_scoring() -> None:
    async def run() -> None:
        from antismurf.vision.lobby_reader import LobbySnapshot

        config = AppConfig(
            memory_enabled=True,
            memory_list_only=True,
            memory_scan_mode="roster",
            memory_auto_enter_lobby=True,
            vision_enabled=False,
        )
        orch = Orchestrator(config)
        host = "5-S2-1-6738824"
        guest = PlayerHandle(
            handle="5-S2-1-12208616",
            slot_index=1,
            display_text="5-S2-1-12208616",
            display_name="GuestName",
            discriminator=12208616,
            server_id=5,
            realm_id=1,
        )
        host_player = PlayerHandle(
            handle=host,
            slot_index=0,
            display_text=host,
            display_name="HostName",
            discriminator=6738824,
            server_id=5,
            realm_id=1,
        )
        snapshot = LobbySnapshot(
            map_name="凯瑞甘生存2",
            map_ocr_text="凯瑞甘生存2",
            host_handle=host,
            local_handle=host,
            is_local_host=True,
            handles=[host_player, guest],
            slot_details=[],
            window_found=True,
            error=None,
        )

        class FakeReader:
            roster_state = type(
                "S",
                (),
                {
                    "phase": "in_room",
                    "in_room": True,
                    "room_created": True,
                    "record_base": 0x1F62EF034F0,
                    "record_base_source": "profile_scan",
                    "member_count": 2,
                },
            )()

            def read_lobby_snapshot(self):
                return snapshot

            def reset_session(self) -> None:
                pass

            def set_lobby_active(self, active: bool) -> None:
                pass

        orch._memory_reader = FakeReader()
        await orch.start()
        try:
            await orch._tick()
            assert host in orch.players
            assert "5-S2-1-12208616" in orch.players
            assert orch.players[host].display_name == "HostName"
            assert orch.players["5-S2-1-12208616"].display_name == "GuestName"
            assert orch.players[host].score == 0
            assert orch.players[host].tier == "low"
            assert not orch.players[host].triggered_rules
        finally:
            await orch.stop()

    asyncio.run(run())


def test_refresh_lobby_now_scans_and_notifies() -> None:
    from types import SimpleNamespace

    class FakeReader:
        def __init__(self) -> None:
            self.roster_state = SimpleNamespace(
                phase="in_room",
                in_room=True,
                room_created=True,
                record_base=0x1234,
                record_base_source="scan",
                member_count=1,
            )

        def read_lobby_snapshot(self):
            return SimpleNamespace(
                error=None,
                handles=[],
                local_handle="5-S2-1-1",
                map_name="凯瑞甘生存2",
                is_local_host=True,
            )

        def set_lobby_active(self, active: bool) -> None:
            pass

    async def run() -> None:
        orch = Orchestrator(AppConfig())
        orch._config.memory_enabled = True
        orch._memory_reader = FakeReader()
        notified: list[tuple] = []
        orch._on_update = lambda *args: notified.append(args)

        ok = await orch.refresh_lobby_now()

        assert ok
        assert orch.last_roster_status.get("in_room") is True
        assert orch._local_handle == "5-S2-1-1"
        assert orch._lobby_active
        assert notified, "手动刷新后应触发通知更新界面"

    asyncio.run(run())


def test_refresh_lobby_now_disabled_without_reader() -> None:
    async def run() -> None:
        orch = Orchestrator(AppConfig())
        orch._config.memory_enabled = False
        orch._memory_reader = None
        ok = await orch.refresh_lobby_now()
        assert not ok

    asyncio.run(run())
