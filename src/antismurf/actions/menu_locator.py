"""Locate and click SC2 lobby context-menu kick entries."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from antismurf.config.settings import _project_root

logger = logging.getLogger(__name__)

# Relative click within matched menu template (2nd item ≈「移出房间」)
_KICK_ITEM_Y_RATIO = 2.0 / 14.0
_KICK_ITEM_X_RATIO = 0.5


def _bundled_target_root() -> Path:
    import sys

    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "target"
    return _project_root() / "target"


def _menu_template_path(configured: str) -> Path | None:
    if configured.strip():
        path = Path(configured)
        if not path.is_absolute():
            path = _project_root() / path
        if path.is_file():
            return path
    root = _bundled_target_root()
    for name in ("kick_menu.png", "移除房间所在菜单.png"):
        candidate = root / name
        if candidate.is_file():
            return candidate
    return None


def detect_kick_menu_remove_region(
    window_title: str,
    menu_template_path: str = "",
    *,
    search_margin_px: int = 480,
    anchor_xy: tuple[int, int] | None = None,
) -> dict[str, float] | None:
    """One-shot template match to locate「移出房间」click (for calibration only)."""
    from antismurf.lobby.sc2_window import find_sc2_window

    template_path = _menu_template_path(menu_template_path)
    window = find_sc2_window(window_title)
    if template_path is None or window is None:
        return None

    try:
        import cv2
        import mss
        import numpy as np
    except ImportError:
        return None

    template = cv2.imread(str(template_path), cv2.IMREAD_COLOR)
    if template is None:
        return None

    th, tw = template.shape[:2]
    with mss.mss() as sct:
        if anchor_xy is not None:
            cx, cy = anchor_xy
            left = max(0, cx - search_margin_px)
            top = max(0, cy - search_margin_px)
            width = search_margin_px * 2
            height = search_margin_px * 2
            monitor = {"left": left, "top": top, "width": width, "height": height}
        else:
            monitor = {
                "left": window.left,
                "top": window.top,
                "width": window.width,
                "height": window.height,
            }
        shot = sct.grab(monitor)
        screen = np.array(shot)[:, :, :3]
        screen_bgr = cv2.cvtColor(screen, cv2.COLOR_RGB2BGR)

    result = cv2.matchTemplate(screen_bgr, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    if max_val < 0.55:
        logger.info("Kick menu calibration detect failed: score=%.3f", max_val)
        return None

    mx, my = max_loc
    click_x = monitor["left"] + mx + int(tw * _KICK_ITEM_X_RATIO)
    click_y = monitor["top"] + my + int(th * _KICK_ITEM_Y_RATIO)
    norm_x = (click_x - window.left) / window.width
    norm_y = (click_y - window.top) / window.height
    logger.info(
        "Kick menu calibrated via template score=%.2f norm=(%.4f, %.4f)",
        max_val,
        norm_x,
        norm_y,
    )
    return {"x": norm_x, "y": norm_y}


def click_kick_menu_item(
    labels: list[str],
    *,
    down_presses: int = 0,
    menu_template_path: str = "",
    search_margin_px: int = 320,
    last_click_xy: tuple[int, int] | None = None,
    menu_wait_sec: float = 0.35,
    retries: int = 3,
) -> bool:
    """Try UIA label match, then template match, then keyboard fallback."""
    from antismurf.actions.context_menu import click_context_menu_item

    for attempt in range(max(1, retries)):
        if attempt:
            time.sleep(0.2)
        if click_context_menu_item(labels, down_presses=0, wait_sec=menu_wait_sec):
            return True
        if _click_via_menu_template(menu_template_path, search_margin_px, last_click_xy):
            return True

    if down_presses > 0:
        return click_context_menu_item([], down_presses=down_presses, wait_sec=0.1)
    return False


def _click_via_menu_template(
    configured_template: str,
    search_margin_px: int,
    last_click_xy: tuple[int, int] | None,
) -> bool:
    template_path = _menu_template_path(configured_template)
    if template_path is None:
        return False

    try:
        import cv2
        import mss
        import numpy as np
        import pyautogui
    except ImportError:
        return False

    template = cv2.imread(str(template_path), cv2.IMREAD_COLOR)
    if template is None:
        return False

    th, tw = template.shape[:2]
    with mss.mss() as sct:
        if last_click_xy is not None:
            cx, cy = last_click_xy
            left = max(0, cx - search_margin_px)
            top = max(0, cy - search_margin_px)
            width = search_margin_px * 2
            height = search_margin_px * 2
            monitor = {"left": left, "top": top, "width": width, "height": height}
        else:
            monitor = sct.monitors[0]

        shot = sct.grab(monitor)
        screen = np.array(shot)[:, :, :3]
        screen_bgr = cv2.cvtColor(screen, cv2.COLOR_RGB2BGR)

    result = cv2.matchTemplate(screen_bgr, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    if max_val < 0.55:
        logger.info("Menu template match score too low: %.3f", max_val)
        return False

    mx, my = max_loc
    click_x = monitor["left"] + mx + int(tw * _KICK_ITEM_X_RATIO)
    click_y = monitor["top"] + my + int(th * _KICK_ITEM_Y_RATIO)
    pyautogui.click(click_x, click_y)
    logger.info(
        "Context menu click via template (score=%.2f) at (%s, %s)",
        max_val,
        click_x,
        click_y,
    )
    time.sleep(0.05)
    return True
