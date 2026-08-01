from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


def click_context_menu_item(
    labels: list[str],
    *,
    down_presses: int = 0,
    wait_sec: float = 0.3,
) -> bool:
    """Click a context menu entry by visible label, with keyboard fallback."""
    if labels and _click_via_uia(labels, wait_sec):
        return True
    return _click_via_keyboard(down_presses)


def _click_via_uia(labels: list[str], wait_sec: float) -> bool:
    time.sleep(wait_sec)
    try:
        from pywinauto import Desktop
    except ImportError:
        return False

    normalized = [label.strip().lower() for label in labels if label.strip()]
    if not normalized:
        return False

    try:
        desktop = Desktop(backend="uia")
        for window in desktop.windows():
            class_name = window.element_info.class_name or ""
            if class_name not in {"Menu", "ContextMenu", "#32768"}:
                continue
            for item in window.descendants():
                try:
                    name = (item.window_text() or "").strip()
                except Exception:
                    continue
                if not name:
                    continue
                name_lower = name.lower()
                if any(label in name_lower or name_lower in label for label in normalized):
                    item.click_input()
                    logger.info("Context menu click via UIA: %s", name)
                    return True
    except Exception as exc:
        logger.debug("UIA context menu lookup failed: %s", exc)
    return False


def _click_via_keyboard(down_presses: int) -> bool:
    try:
        import pyautogui

        for _ in range(down_presses):
            pyautogui.press("down")
            time.sleep(0.05)
        pyautogui.press("enter")
        return True
    except Exception as exc:
        logger.error("Keyboard context menu selection failed: %s", exc)
        return False
