"""Fullscreen drag-to-mark overlay for kick UI calibration."""

from __future__ import annotations

import logging
import tkinter as tk
from typing import Callable

from antismurf.lobby.capture import sample_cursor_relative

logger = logging.getLogger(__name__)


def _restore_parent(parent: tk.Misc) -> None:
    try:
        parent.deiconify()
        parent.lift()
        parent.focus_force()
    except tk.TclError:
        pass


def run_drag_mark(
    parent: tk.Misc,
    instruction: str,
    on_complete: Callable[[int, int], None],
    *,
    window_title: str = "StarCraft II",
    on_cancel: Callable[[], None] | None = None,
) -> None:
    """Show a topmost fullscreen overlay with a crosshair that follows the mouse."""
    overlay: tk.Toplevel | None = None
    try:
        overlay = tk.Toplevel(parent)
        overlay.withdraw()
        overlay.transient(parent)
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True)
        try:
            overlay.attributes("-alpha", 0.22)
        except tk.TclError:
            pass
        overlay.configure(bg="#000000")

        screen_w = overlay.winfo_screenwidth()
        screen_h = overlay.winfo_screenheight()
        overlay.geometry(f"{screen_w}x{screen_h}+0+0")

        header = tk.Frame(overlay, bg="#000000")
        header.pack(fill="x", side="top")
        tk.Label(
            header,
            text=instruction,
            font=("Microsoft YaHei UI", 16, "bold"),
            fg="#00ff88",
            bg="#000000",
            wraplength=min(1200, screen_w - 40),
            justify="left",
            padx=20,
            pady=10,
        ).pack(anchor="w")
        tk.Label(
            header,
            text="移动鼠标即可看到绿色准星 → 按住左键拖到目标 → 松开确认 | Esc 取消",
            font=("Microsoft YaHei UI", 12),
            fg="#ffffff",
            bg="#000000",
            padx=20,
            pady=8,
        ).pack(anchor="w")

        canvas = tk.Canvas(
            overlay,
            highlightthickness=0,
            bg="#101010",
            cursor="crosshair",
        )
        canvas.pack(fill="both", expand=True)

        coord_label = tk.Label(
            overlay,
            text="准备就绪 — 请移动鼠标",
            font=("Consolas", 13, "bold"),
            fg="#ffff00",
            bg="#000000",
        )
        coord_label.pack(side="bottom", fill="x", pady=6)

        state = {
            "dragging": False,
            "last_x": screen_w // 2,
            "last_y": screen_h // 2,
            "finished": False,
        }

        def finish(screen_x: int, screen_y: int) -> None:
            if state["finished"]:
                return
            state["finished"] = True
            try:
                overlay.grab_release()
            except tk.TclError:
                pass
            overlay.destroy()
            _restore_parent(parent)
            on_complete(screen_x, screen_y)

        def cancel() -> None:
            if state["finished"]:
                return
            state["finished"] = True
            try:
                overlay.grab_release()
            except tk.TclError:
                pass
            overlay.destroy()
            _restore_parent(parent)
            if on_cancel:
                on_cancel()

        def format_coords(screen_x: int, screen_y: int) -> str:
            sample = sample_cursor_relative(window_title)
            base = f"屏幕 ({screen_x}, {screen_y})"
            if sample.get("in_window") and sample.get("rel_x") is not None:
                return (
                    f"{base}  |  SC2 相对 x={sample['rel_x']:.4f}  y={sample['rel_y']:.4f}"
                )
            if sample.get("window_found"):
                return f"{base}  |  （光标不在 SC2 窗口内）"
            return f"{base}  |  （未找到 SC2 窗口）"

        def draw_crosshair(cx: int, cy: int, *, dragging: bool) -> None:
            canvas.delete("cross")
            w = max(canvas.winfo_width(), 1)
            h = max(canvas.winfo_height(), 1)
            cx = max(0, min(cx, w))
            cy = max(0, min(cy, h))

            line_color = "#00ff00" if dragging else "#66ff66"
            line_w = 3 if dragging else 2
            r = 18 if dragging else 14

            canvas.create_line(0, cy, w, cy, fill=line_color, width=line_w, tags="cross")
            canvas.create_line(cx, 0, cx, h, fill=line_color, width=line_w, tags="cross")
            canvas.create_oval(
                cx - r,
                cy - r,
                cx + r,
                cy + r,
                outline="#00ff00" if dragging else "#88ff88",
                width=4 if dragging else 2,
                tags="cross",
            )
            canvas.create_oval(
                cx - 3,
                cy - 3,
                cx + 3,
                cy + 3,
                fill="#ffffff",
                outline="#ffffff",
                tags="cross",
            )

            root_x = canvas.winfo_rootx() + cx
            root_y = canvas.winfo_rooty() + cy
            coord_label.configure(text=format_coords(root_x, root_y))
            state["last_x"] = cx
            state["last_y"] = cy

        def on_motion(event: tk.Event) -> None:
            draw_crosshair(int(event.x), int(event.y), dragging=state["dragging"])

        def on_press(event: tk.Event) -> None:
            state["dragging"] = True
            draw_crosshair(int(event.x), int(event.y), dragging=True)

        def on_release(event: tk.Event) -> None:
            if not state["dragging"]:
                return
            state["dragging"] = False
            cx, cy = int(event.x), int(event.y)
            root_x = canvas.winfo_rootx() + cx
            root_y = canvas.winfo_rooty() + cy
            finish(root_x, root_y)

        def on_escape(_event: tk.Event | None = None) -> None:
            cancel()

        def sync_mouse_from_system() -> None:
            if state["finished"]:
                return
            try:
                import pyautogui

                mx, my = pyautogui.position()
                cx = mx - canvas.winfo_rootx()
                cy = my - canvas.winfo_rooty()
                w = canvas.winfo_width() or screen_w
                h = canvas.winfo_height() or screen_h
                if 0 <= cx <= w and 0 <= cy <= h:
                    draw_crosshair(int(cx), int(cy), dragging=state["dragging"])
            except Exception:
                pass
            overlay.after(30, sync_mouse_from_system)

        canvas.bind("<Enter>", on_motion)
        canvas.bind("<Motion>", on_motion)
        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_motion)
        canvas.bind("<ButtonRelease-1>", on_release)
        overlay.bind("<Escape>", on_escape)

        overlay.update_idletasks()
        try:
            parent.withdraw()
        except tk.TclError:
            pass

        overlay.deiconify()
        overlay.lift()
        overlay.attributes("-topmost", True)
        overlay.focus_force()
        try:
            overlay.grab_set()
        except tk.TclError:
            pass

        canvas.after(
            80,
            lambda: draw_crosshair(state["last_x"], state["last_y"], dragging=False),
        )
        overlay.after(100, sync_mouse_from_system)

    except Exception:
        logger.exception("Failed to open calibration drag overlay")
        if overlay is not None:
            try:
                overlay.destroy()
            except tk.TclError:
                pass
        _restore_parent(parent)
        if on_cancel:
            on_cancel()
        raise
