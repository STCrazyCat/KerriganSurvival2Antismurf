import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import antismurf.lobby.sc2_process as sp


def test_resolve_sc2_pid_uses_running_process_without_title_match() -> None:
    original_pids = sp.list_sc2_pids
    original_windows = sp.list_sc2_windows
    original_foreground = sp.get_foreground_window_pid

    sp.list_sc2_pids = lambda *_a, **_k: [4242]
    sp.list_sc2_windows = lambda *_a, **_k: []
    sp.get_foreground_window_pid = lambda *_a, **_k: None
    try:
        pid = sp.resolve_sc2_pid(title_hints=("StarCraft II",))
        assert pid == 4242
    finally:
        sp.list_sc2_pids = original_pids
        sp.list_sc2_windows = original_windows
        sp.get_foreground_window_pid = original_foreground


def test_resolve_sc2_pid_honors_target_pid() -> None:
    original_pids = sp.list_sc2_pids
    sp.list_sc2_pids = lambda *_a, **_k: [111, 222]
    try:
        assert sp.resolve_sc2_pid(target_pid=222) == 222
        assert sp.resolve_sc2_pid(target_pid=999) is None
    finally:
        sp.list_sc2_pids = original_pids


def test_resolve_sc2_pid_prefers_single_visible_window() -> None:
    original_pids = sp.list_sc2_pids
    original_windows = sp.list_sc2_windows
    original_foreground = sp.get_foreground_window_pid

    window = sp.Sc2WindowInfo(hwnd=1, pid=5555, title="星际争霸 II")
    sp.list_sc2_pids = lambda *_a, **_k: [5555, 6666]
    sp.list_sc2_windows = lambda *_a, **_k: [window]
    sp.get_foreground_window_pid = lambda *_a, **_k: None
    try:
        assert sp.resolve_sc2_pid() == 5555
    finally:
        sp.list_sc2_pids = original_pids
        sp.list_sc2_windows = original_windows
        sp.get_foreground_window_pid = original_foreground
