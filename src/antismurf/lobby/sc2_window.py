from __future__ import annotations

import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_FALLBACK_TITLE_NEEDLES = ("星际争霸", "StarCraft II", "StarCraft")


@dataclass
class WindowRect:
    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height


def _title_candidates(title_contains: str) -> tuple[str, ...]:
    primary = (title_contains or "").strip()
    seen: set[str] = set()
    ordered: list[str] = []
    for needle in (primary, *_FALLBACK_TITLE_NEEDLES):
        if not needle or needle in seen:
            continue
        seen.add(needle)
        ordered.append(needle)
    return tuple(ordered)


def find_sc2_hwnd(title_contains: str = "StarCraft II") -> int | None:
    try:
        import win32gui
    except ImportError:
        return None

    for needle in _title_candidates(title_contains):
        found: int | None = None

        def callback(h: int, _: object) -> bool:
            nonlocal found
            if not win32gui.IsWindowVisible(h):
                return True
            title = win32gui.GetWindowText(h)
            if needle.lower() in title.lower():
                found = h
                return False
            return True

        win32gui.EnumWindows(callback, None)
        if found is not None:
            return found
    return None


def find_sc2_window(title_contains: str = "StarCraft II") -> WindowRect | None:
    """Return SC2 **client area** in screen coordinates (works for windowed maximized)."""
    hwnd = find_sc2_hwnd(title_contains)
    if hwnd is None:
        return None
    return client_area_rect(hwnd)


def client_area_rect(hwnd: int) -> WindowRect | None:
    try:
        import win32gui
    except ImportError:
        return None

    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    screen_left, screen_top = win32gui.ClientToScreen(hwnd, (left, top))
    screen_right, screen_bottom = win32gui.ClientToScreen(hwnd, (right, bottom))
    width = max(1, screen_right - screen_left)
    height = max(1, screen_bottom - screen_top)
    return WindowRect(screen_left, screen_top, width, height)


def is_sc2_foreground(title_contains: str = "StarCraft II") -> bool:
    try:
        import win32gui
    except ImportError:
        return False

    hwnd = find_sc2_hwnd(title_contains)
    if hwnd is None:
        return False
    return win32gui.GetForegroundWindow() == hwnd


def activate_sc2_window(title_contains: str = "StarCraft II", *, wait_sec: float = 0.2) -> bool:
    """Bring SC2 to foreground; returns True only if it becomes the active window."""
    try:
        import win32con
        import win32gui
        import win32process
    except ImportError:
        return False

    hwnd = find_sc2_hwnd(title_contains)
    if hwnd is None:
        logger.warning("SC2 window not found (titles tried: %s)", _title_candidates(title_contains))
        return False

    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    else:
        win32gui.ShowWindow(hwnd, win32con.SW_SHOW)

    foreground = win32gui.GetForegroundWindow()
    if foreground != hwnd:
        fg_thread, _ = win32process.GetWindowThreadProcessId(foreground)
        target_thread, _ = win32process.GetWindowThreadProcessId(hwnd)
        attached = False
        try:
            if fg_thread and target_thread and fg_thread != target_thread:
                win32process.AttachThreadInput(fg_thread, target_thread, True)
                attached = True
            win32gui.SetForegroundWindow(hwnd)
            win32gui.BringWindowToTop(hwnd)
        finally:
            if attached:
                win32process.AttachThreadInput(fg_thread, target_thread, False)

    time.sleep(wait_sec)
    active = win32gui.GetForegroundWindow() == hwnd
    if not active:
        logger.warning(
            "SC2 window found but could not take foreground (hwnd=%s, active=%s)",
            hwnd,
            win32gui.GetForegroundWindow(),
        )
    return active
