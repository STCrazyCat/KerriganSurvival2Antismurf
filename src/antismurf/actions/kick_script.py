"""Deterministic kick via calibrated coordinates (pyautogui script, no OCR/UIA)."""

from __future__ import annotations

import logging
import time

from antismurf.actions.kick_calibration import derive_slot_regions, menu_click_from_slot
from antismurf.config.kick_defaults import LOBBY_UI_SLOT_COUNT, ui_slot_label
from antismurf.config.settings import AppConfig
from antismurf.lobby.sc2_window import WindowRect, activate_sc2_window, find_sc2_window

logger = logging.getLogger(__name__)


def _slot_region(config: AppConfig, slot_index: int) -> dict[str, float] | None:
    regions = config.slot_regions
    if slot_index < len(regions):
        return regions[slot_index]
    if regions and config.kick_slot_step:
        derived = derive_slot_regions(regions[0], config.kick_slot_step)
        if slot_index < len(derived):
            return derived[slot_index]
    return None


def kick_player_slot(
    config: AppConfig,
    slot_index: int,
    *,
    window: WindowRect | None = None,
) -> bool:
    """Right-click slot anchor, then left-click menu point from fixed offset."""
    if slot_index < 0 or slot_index >= LOBBY_UI_SLOT_COUNT:
        return False

    region = _slot_region(config, slot_index)
    if region is None:
        logger.error("Kick script: slot %s not calibrated", ui_slot_label(slot_index))
        return False

    title = config.window_title_contains
    if window is None:
        if not activate_sc2_window(title, wait_sec=config.kick_focus_wait_sec):
            return False
        window = find_sc2_window(title)
    if window is None:
        return False

    slot_x = int(window.left + window.width * float(region["x"]))
    slot_y = int(window.top + window.height * float(region["y"]))

    menu_x: int | None = None
    menu_y: int | None = None
    offset = config.kick_menu_offset
    if offset and offset.get("dx") is not None and offset.get("dy") is not None:
        menu_norm = menu_click_from_slot(region, offset)
        menu_x = int(window.left + window.width * float(menu_norm["x"]))
        menu_y = int(window.top + window.height * float(menu_norm["y"]))
    elif config.kick_menu_remove_region.get("x") is not None:
        menu_norm = config.kick_menu_remove_region
        menu_x = int(window.left + window.width * float(menu_norm["x"]))
        menu_y = int(window.top + window.height * float(menu_norm["y"]))

    if menu_x is None or menu_y is None:
        logger.error("Kick script: menu offset not calibrated")
        return False

    try:
        import pyautogui

        pyautogui.click(slot_x, slot_y, button="right")
        time.sleep(max(0.15, config.kick_menu_open_wait_sec))
        pyautogui.click(menu_x, menu_y)
        logger.info(
            "Kick script slot %s: right (%s,%s) menu (%s,%s)",
            ui_slot_label(slot_index),
            slot_x,
            slot_y,
            menu_x,
            menu_y,
        )
        return True
    except Exception as exc:
        logger.error("Kick script failed: %s", exc)
        return False


def sc2_right_click_screen(
    config: AppConfig,
    screen_x: int,
    screen_y: int,
) -> bool:
    """Focus SC2 and right-click absolute screen coordinates."""
    if not activate_sc2_window(
        config.window_title_contains, wait_sec=config.kick_focus_wait_sec
    ):
        return False
    try:
        import pyautogui

        pyautogui.click(screen_x, screen_y, button="right")
        return True
    except Exception:
        return False
