from __future__ import annotations

import logging
import time

from antismurf.actions.context_menu import click_context_menu_item
from antismurf.config.settings import AppConfig
from antismurf.lobby.sc2_window import activate_sc2_window, find_sc2_window
from antismurf.review.profile_parser import Sc2ProfileRef, parse_profile_ids_text
from antismurf.utils.clipboard import copy_to_clipboard, read_clipboard

logger = logging.getLogger(__name__)


class ProfileAssist:
    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def open_profile_via_slot(self, slot_index: int) -> bool:
        if not activate_sc2_window(self._config.window_title_contains):
            return False
        region = self._slot_region(slot_index)
        if region is None:
            return False
        window = find_sc2_window(self._config.window_title_contains)
        if window is None:
            return False
        x = int(window.left + window.width * region.get("x", 0.5))
        y = int(window.top + window.height * region.get("y", 0.5))
        try:
            import pyautogui

            pyautogui.click(x, y, button="right")
            time.sleep(0.25)
            if not click_context_menu_item(
                self._config.profile_menu_labels,
                down_presses=self._config.profile_menu_down_presses,
            ):
                logger.error("Profile menu selection failed for slot %s", slot_index)
                return False
            return True
        except Exception as exc:
            logger.error("Slot profile open failed: %s", exc)
            return False

    def _slot_region(self, slot_index: int) -> dict[str, float] | None:
        regions = self._config.slot_regions
        if slot_index < len(regions):
            return regions[slot_index]
        return None

    def open_profile(self, handle: str, slot_index: int | None = None) -> bool:
        if slot_index is not None and self._config.slot_regions:
            if self.open_profile_via_slot(slot_index):
                logger.info("Opened profile via slot %s for %s", slot_index, handle)
                return True
        if not activate_sc2_window(self._config.window_title_contains):
            logger.warning("SC2 window not found")
            return False
        time.sleep(0.3)
        try:
            import pyautogui

            pyautogui.press("enter")
            time.sleep(0.1)
            command = f"/profile {handle}"
            if copy_to_clipboard(command):
                pyautogui.hotkey("ctrl", "v")
            else:
                pyautogui.write(command, interval=0.02)
            pyautogui.press("enter")
            logger.info("Sent profile command for %s", handle)
            return True
        except Exception as exc:
            logger.error("Failed to open profile: %s", exc)
            return False

    def try_read_profile_ref_from_clipboard(self) -> Sc2ProfileRef | None:
        text = read_clipboard()
        if not text:
            return None
        return parse_profile_ids_text(text)
