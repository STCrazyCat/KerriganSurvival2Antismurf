from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010

DEFAULT_SC2_PROCESS_NAMES = ("SC2_x64.exe", "SC2.exe")
DEFAULT_SC2_TITLE_HINTS = (
    "StarCraft II",
    "StarCraft",
    "星际争霸",
    "星海争霸",
    "스타크래프트",
)


def list_sc2_pids(process_names: list[str] | tuple[str, ...] | None = None) -> list[int]:
    """Return process ids for running StarCraft II clients."""
    names = {name.lower() for name in (process_names or DEFAULT_SC2_PROCESS_NAMES)}
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return []

    TH32CS_SNAPPROCESS = 0x00000002
    kernel32 = ctypes.windll.kernel32

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_char * 260),
        ]

    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        return []

    entry = PROCESSENTRY32()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
    pids: list[int] = []
    try:
        if not kernel32.Process32First(snapshot, ctypes.byref(entry)):
            return []
        while True:
            exe = entry.szExeFile.decode("utf-8", errors="ignore")
            if exe.lower() in names:
                pids.append(int(entry.th32ProcessID))
            if not kernel32.Process32Next(snapshot, ctypes.byref(entry)):
                break
    finally:
        kernel32.CloseHandle(snapshot)
    return sorted(set(pids))


def get_foreground_window_pid(title_contains: str) -> int | None:
    try:
        import win32gui
        import win32process
    except ImportError:
        return None

    hwnd: int | None = None

    def callback(h: int, _: object) -> bool:
        nonlocal hwnd
        if not win32gui.IsWindowVisible(h):
            return True
        title = win32gui.GetWindowText(h)
        if title_contains.lower() in title.lower():
            hwnd = h
            return False
        return True

    win32gui.EnumWindows(callback, None)
    if hwnd is None:
        return None
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    return int(pid) if pid else None


def resolve_sc2_pid(
    *,
    process_names: list[str] | tuple[str, ...] | None = None,
    target_pid: int | None = None,
    title_hints: list[str] | tuple[str, ...] | None = None,
) -> int | None:
    """Resolve SC2 PID for memory reads (process-first, like probe Mode 6)."""
    names = list(process_names or DEFAULT_SC2_PROCESS_NAMES)
    hints = tuple(title_hints or DEFAULT_SC2_TITLE_HINTS)
    pids = list_sc2_pids(names)
    if not pids:
        return None

    if target_pid is not None and int(target_pid) > 0:
        if int(target_pid) in pids:
            return int(target_pid)
        logger.warning("Selected SC2 pid %s is not running", target_pid)
        return None

    windows = list_sc2_windows(names)
    if len(windows) == 1:
        return windows[0].pid

    for hint in hints:
        foreground_pid = get_foreground_window_pid(hint)
        if foreground_pid is not None and foreground_pid in pids:
            return foreground_pid

    if windows:
        unique_pids = sorted({item.pid for item in windows})
        if len(unique_pids) == 1:
            return unique_pids[0]
        logger.info(
            "Multiple SC2 windows %s; using pid %s (select process in UI)",
            unique_pids,
            windows[0].pid,
        )
        return windows[0].pid

    if len(pids) == 1:
        return pids[0]

    logger.info(
        "Multiple SC2 processes %s; using pid %s (select process in UI)",
        pids,
        pids[0],
    )
    return pids[0]


def get_sc2_pid(
    *,
    window_title_contains: str = "StarCraft II",
    process_names: list[str] | tuple[str, ...] | None = None,
    target_pid: int | None = None,
) -> int | None:
    """Prefer the SC2 process that owns the visible lobby window."""
    hints = (window_title_contains, *DEFAULT_SC2_TITLE_HINTS)
    return resolve_sc2_pid(
        process_names=process_names,
        target_pid=target_pid,
        title_hints=hints,
    )


def open_process_for_read(pid: int):
    import ctypes

    handle = ctypes.windll.kernel32.OpenProcess(
        PROCESS_QUERY_INFORMATION | PROCESS_VM_READ,
        False,
        int(pid),
    )
    if not handle:
        raise OSError(f"OpenProcess failed for pid {pid}")
    return handle


def close_process(handle) -> None:
    if not handle:
        return
    import ctypes

    ctypes.windll.kernel32.CloseHandle(handle)


@dataclass(frozen=True)
class Sc2WindowInfo:
    hwnd: int
    pid: int
    title: str

    @property
    def label(self) -> str:
        short = self.title if len(self.title) <= 60 else self.title[:57] + "..."
        return f"PID {self.pid} | {short}"


def list_sc2_windows(
    process_names: list[str] | tuple[str, ...] | None = None,
) -> list[Sc2WindowInfo]:
    """List visible top-level windows owned by SC2 processes."""
    try:
        import win32gui
        import win32process
    except ImportError:
        return []

    pids = set(list_sc2_pids(process_names))
    if not pids:
        return []

    found: list[Sc2WindowInfo] = []

    def callback(hwnd: int, _: object) -> bool:
        if not win32gui.IsWindowVisible(hwnd):
            return True
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if int(pid) not in pids:
            return True
        title = win32gui.GetWindowText(hwnd).strip()
        if not title:
            title = "(SC2 窗口)"
        found.append(Sc2WindowInfo(hwnd=int(hwnd), pid=int(pid), title=title))
        return True

    win32gui.EnumWindows(callback, None)
    found.sort(key=lambda item: (item.pid, item.title))

    seen_pids = {item.pid for item in found}
    for pid in sorted(pids):
        if pid not in seen_pids:
            found.append(
                Sc2WindowInfo(
                    hwnd=0,
                    pid=int(pid),
                    title="(进程运行中，无可见窗口标题)",
                )
            )
    return found
