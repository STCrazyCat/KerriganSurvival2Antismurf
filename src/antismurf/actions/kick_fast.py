"""Fast kick execution using pre-calibrated coordinates (no per-kick OCR)."""

from __future__ import annotations

import logging
import time

from antismurf.actions.kick_calibration import menu_click_from_slot
from antismurf.config.settings import AppConfig
from antismurf.lobby.sc2_window import WindowRect

logger = logging.getLogger(__name__)


def click_kick_menu_fast(
    config: AppConfig,
    window: WindowRect,
    *,
    slot_click_xy: tuple[int, int] | None = None,
    slot_region: dict[str, float] | None = None,
) -> bool:
    """Select「移出房间」via offset/ calibrated coords or keyboard (no OCR)."""
    try:
        import pyautogui
    except ImportError:
        return False

    click_x: int | None = None
    click_y: int | None = None

    offset = config.kick_menu_offset
    if (
        offset
        and offset.get("dx") is not None
        and offset.get("dy") is not None
        and slot_region is not None
    ):
        menu_norm = menu_click_from_slot(slot_region, offset)
        click_x = int(window.left + window.width * menu_norm["x"])
        click_y = int(window.top + window.height * menu_norm["y"])
    elif config.kick_menu_remove_region.get("x") is not None:
        region = config.kick_menu_remove_region
        click_x = int(window.left + window.width * float(region["x"]))
        click_y = int(window.top + window.height * float(region["y"]))

    if click_x is not None and click_y is not None:
        pyautogui.click(click_x, click_y)
        logger.info("Kick menu fast click at (%s, %s)", click_x, click_y)
        return True

    presses = max(1, config.kick_menu_down_presses)
    for _ in range(presses):
        pyautogui.press("down")
        time.sleep(0.03)
    pyautogui.press("enter")
    logger.info(
        "Kick menu fast keyboard (%s down + enter)%s",
        presses,
        f" after slot click {slot_click_xy}" if slot_click_xy else "",
    )
    return True
