from __future__ import annotations

import logging
import time

from antismurf.lobby.sc2_window import find_sc2_window

logger = logging.getLogger(__name__)


def capture_relative_point(
    window_title_contains: str = "StarCraft II",
    countdown_sec: float = 3.0,
) -> tuple[float, float] | None:
    """After countdown, return cursor position as fraction of SC2 window."""
    window = find_sc2_window(window_title_contains)
    if window is None:
        logger.warning("SC2 window not found for capture")
        return None

    time.sleep(max(0.0, countdown_sec))

    try:
        import pyautogui

        x, y = pyautogui.position()
    except Exception as exc:
        logger.error("Cursor capture failed: %s", exc)
        return None

    rel_x = (x - window.left) / window.width
    rel_y = (y - window.top) / window.height
    if not (0.0 <= rel_x <= 1.0 and 0.0 <= rel_y <= 1.0):
        logger.warning("Cursor outside SC2 window: %.3f, %.3f", rel_x, rel_y)
        return None
    return rel_x, rel_y


def point_to_region(
    rel_x: float,
    rel_y: float,
    width: float = 0.28,
    height: float = 0.045,
) -> dict[str, float]:
    x = max(0.0, rel_x - width / 2)
    y = max(0.0, rel_y - height / 2)
    if x + width > 1.0:
        x = 1.0 - width
    if y + height > 1.0:
        y = 1.0 - height
    return {"x": round(x, 4), "y": round(y, 4), "w": width, "h": height}


def point_to_id_region(rel_x: float, rel_y: float) -> dict[str, float]:
    return point_to_region(rel_x, rel_y, width=0.18, height=0.035)


def screen_point_to_slot_region(
    screen_x: int,
    screen_y: int,
    window_title_contains: str = "StarCraft II",
) -> dict[str, float] | None:
    """Convert absolute screen pixel to normalized slot coordinate within SC2 client."""
    window = find_sc2_window(window_title_contains)
    if window is None:
        return None
    rel_x = (screen_x - window.left) / window.width
    rel_y = (screen_y - window.top) / window.height
    return point_to_slot_region(rel_x, rel_y)


def point_to_slot_region(rel_x: float, rel_y: float) -> dict[str, float]:
    return {"x": round(rel_x, 6), "y": round(rel_y, 6)}


def sample_cursor_relative(
    window_title_contains: str = "StarCraft II",
) -> dict[str, object]:
    """Current cursor position in screen pixels and SC2 client-relative fractions."""
    window = find_sc2_window(window_title_contains)
    try:
        import pyautogui

        screen_x, screen_y = pyautogui.position()
    except Exception as exc:
        logger.debug("Cursor sample failed: %s", exc)
        return {
            "screen_x": 0,
            "screen_y": 0,
            "rel_x": None,
            "rel_y": None,
            "in_window": False,
            "window_found": window is not None,
        }

    if window is None:
        return {
            "screen_x": screen_x,
            "screen_y": screen_y,
            "rel_x": None,
            "rel_y": None,
            "in_window": False,
            "window_found": False,
        }

    rel_x = (screen_x - window.left) / window.width
    rel_y = (screen_y - window.top) / window.height
    in_window = 0.0 <= rel_x <= 1.0 and 0.0 <= rel_y <= 1.0
    return {
        "screen_x": screen_x,
        "screen_y": screen_y,
        "rel_x": round(rel_x, 6) if in_window else round(rel_x, 6),
        "rel_y": round(rel_y, 6) if in_window else round(rel_y, 6),
        "in_window": in_window,
        "window_found": True,
    }
