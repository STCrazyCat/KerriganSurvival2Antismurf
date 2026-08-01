import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.config.kick_defaults import (
    LOBBY_UI_SLOT_COUNT,
    default_slot_regions,
    pad_slot_regions,
    ui_slot_label,
)
from antismurf.lobby.memory_lobby_auto_confirm import evaluate_lobby_snapshot
from antismurf.lobby.memory_lobby_roster import parse_lobby_member_record


def test_default_slot_regions_has_ten_entries() -> None:
    regions = default_slot_regions()
    assert len(regions) == LOBBY_UI_SLOT_COUNT == 10


def test_pad_slot_regions_extends_eight_to_ten() -> None:
    base = [{"x": 0.124, "y": 0.32 + i * 0.066} for i in range(8)]
    padded = pad_slot_regions(base)
    assert len(padded) == 10
    assert padded[8]["y"] > padded[7]["y"]


def test_ui_slot_label_is_one_based() -> None:
    assert ui_slot_label(0) == "1"
    assert ui_slot_label(9) == "10"


def test_kick_script_clicks_slot_and_menu(monkeypatch) -> None:
    from antismurf.actions.kick_script import kick_player_slot
    from antismurf.config.settings import AppConfig
    from antismurf.lobby.sc2_window import WindowRect

    clicks: list[tuple[int, int, str | None]] = []

    class FakeGui:
        @staticmethod
        def click(x: int, y: int, button: str = "left") -> None:
            clicks.append((x, y, button))

    monkeypatch.setitem(sys.modules, "pyautogui", FakeGui())
    cfg = AppConfig(
        slot_regions=[{"x": 0.1, "y": 0.2}],
        kick_menu_offset={"dx": 0.05, "dy": 0.07},
        kick_menu_open_wait_sec=0.01,
    )
    window = WindowRect(0, 0, 1000, 800)
    assert kick_player_slot(cfg, 0, window=window) is True
    assert len(clicks) == 2
    assert clicks[0] == (100, 160, "right")
    assert clicks[1][0] == 150
    assert clicks[1][1] == 216


def test_click_kick_menu_fast_uses_keyboard(monkeypatch) -> None:
    from antismurf.actions.kick_fast import click_kick_menu_fast
    from antismurf.config.settings import AppConfig
    from antismurf.lobby.sc2_window import WindowRect

    presses: list[str] = []

    class FakeGui:
        @staticmethod
        def click(*_args, **_kwargs) -> None:
            pass

        @staticmethod
        def press(key: str) -> None:
            presses.append(key)

    monkeypatch.setitem(sys.modules, "pyautogui", FakeGui())
    cfg = AppConfig(kick_menu_down_presses=1, kick_menu_remove_region={})
    window = WindowRect(0, 0, 1920, 1080)
    assert click_kick_menu_fast(cfg, window) is True
    assert presses == ["down", "enter"]


def test_click_kick_menu_fast_uses_calibrated_point(monkeypatch) -> None:
    from antismurf.actions.kick_fast import click_kick_menu_fast
    from antismurf.config.settings import AppConfig
    from antismurf.lobby.sc2_window import WindowRect

    clicks: list[tuple[int, int]] = []

    class FakeGui:
        @staticmethod
        def click(x: int, y: int, **_kwargs) -> None:
            clicks.append((x, y))

        @staticmethod
        def press(_key: str) -> None:
            raise AssertionError("keyboard should not be used")

    monkeypatch.setitem(sys.modules, "pyautogui", FakeGui())
    cfg = AppConfig(kick_menu_remove_region={"x": 0.5, "y": 0.5})
    window = WindowRect(100, 50, 800, 600)
    assert click_kick_menu_fast(cfg, window) is True
    assert clicks == [(500, 350)]


def test_apply_manual_menu_offset() -> None:
    from antismurf.actions.kick_calibration import apply_manual_menu_offset

    result = apply_manual_menu_offset(
        {"x": 0.12, "y": 0.32},
        {"x": 0.18, "y": 0.39},
    )
    assert result.ok
    assert result.menu_offset == {"dx": 0.06, "dy": 0.07}


def test_apply_slot_step_from_two_anchors() -> None:
    from antismurf.actions.kick_calibration import (
        apply_slot_step_from_two_anchors,
        derive_slot_regions,
    )

    result = apply_slot_step_from_two_anchors(
        {"x": 0.12, "y": 0.32},
        {"x": 0.12, "y": 0.386},
    )
    assert result.ok
    slots = derive_slot_regions({"x": 0.12, "y": 0.32}, result.slot_step or {})
    assert len(slots) == 10


def test_apply_spectator_calibration_generates_ten_slots() -> None:
    from antismurf.actions.kick_calibration import apply_spectator_calibration

    result = apply_spectator_calibration(
        {"x": 0.12, "y": 0.32},
        {"x": 0.18, "y": 0.39},
        slot_step={"dx": 0.0, "dy": 0.066},
    )
    assert result.ok
    assert result.menu_offset == {"dx": 0.06, "dy": 0.07}
    from antismurf.actions.kick_calibration import derive_slot_regions

    slots = derive_slot_regions({"x": 0.12, "y": 0.32}, {"dx": 0.0, "dy": 0.066})
    assert len(slots) == 10
    assert slots[1]["y"] == pytest.approx(0.386)


def test_community_match_count_from_roles() -> None:
    from antismurf.data.profile_builder import build_profile_from_ks2_wiki

    profile = build_profile_from_ks2_wiki(
        "5-S2-1-100",
        {
            "cores": {"kerrigan": 1000, "survivor": 1000},
            "roles_kerrigan": [{"role_name": "A", "plays": 12, "wins": 6}],
            "roles_survivor": [{"role_name": "B", "plays": 8, "wins": 4}],
        },
    )
    assert profile.derived.data_quality.community_match_count == 20

    from tests.test_memory_lobby_auto_confirm import _build_record

    host = parse_lobby_member_record(
        bytes(_build_record(6738824, "Host")),
        record_base=0x2000,
        rel_base=0,
    )
    guest = parse_lobby_member_record(
        bytes(_build_record(1111111, "Guest")),
        record_base=0x1000,
        rel_base=0,
    )
    assert host is not None and guest is not None
    _, in_room, room_created = evaluate_lobby_snapshot(
        host_handle=host.handle,
        record_base=0x2000,
        members=[(0, guest), (1, host)],
    )
    assert in_room is True
    assert room_created is False
