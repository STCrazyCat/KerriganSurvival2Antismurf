import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.config.settings import AppConfig
from antismurf.lobby.map_guard import MapGuard


def test_map_guard_enter_on_ks2_map_and_players() -> None:
    guard = MapGuard(AppConfig())
    event = guard.update("凯瑞甘生存2", lobby_player_count=2)
    assert event == "enter"
    assert guard.is_active


def test_map_guard_exit_after_mismatch_ticks() -> None:
    guard = MapGuard(AppConfig())
    guard.update("凯瑞甘生存2", lobby_player_count=2)
    event = None
    for _ in range(3):
        event = guard.update(None, lobby_player_count=0)
    assert event == "exit"
    assert not guard.is_active


def test_map_guard_ignores_map_without_players() -> None:
    guard = MapGuard(AppConfig())
    assert guard.update("凯瑞甘生存2", lobby_player_count=0) is None
    assert not guard.is_active


def test_map_guard_manual_lock_prevents_auto_exit() -> None:
    guard = MapGuard(AppConfig())
    guard.force_active("凯瑞甘生存2", manual=True)
    assert guard.is_active
    assert guard.manual_lock
    for _ in range(5):
        assert guard.update(None, lobby_player_count=0) is None
    assert guard.is_active


def test_map_guard_release_manual_allows_exit() -> None:
    guard = MapGuard(AppConfig())
    guard.force_active("凯瑞甘生存2", manual=True)
    guard.release_manual()
    event = None
    for _ in range(3):
        event = guard.update(None, lobby_player_count=0)
    assert event == "exit"
