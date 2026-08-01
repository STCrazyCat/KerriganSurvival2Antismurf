from __future__ import annotations

import threading
from typing import Callable

import customtkinter as ctk

from antismurf.actions.kick_calibration import apply_manual_menu_offset, normalized_offset
from antismurf.config.kick_defaults import LOBBY_UI_SLOT_COUNT
from antismurf.config.settings import AppConfig, save_user_calibration
from antismurf.lobby.capture import screen_point_to_slot_region
from antismurf.app.calibration_drag import run_drag_mark


class CalibrationWizard(ctk.CTkToplevel):
    """Fixed drag-based kick calibration: slot 1 + menu offset + slots 2-10."""

    def __init__(
        self,
        parent: ctk.CTk,
        config: AppConfig,
        on_saved: Callable[[AppConfig], None] | None = None,
        orchestrator=None,
    ) -> None:
        super().__init__(parent)
        self.title("UI 校准")
        self.geometry("520x480")
        self._config = config
        self._on_saved = on_saved
        self._orchestrator = orchestrator
        self._slot_regions: list[dict[str, float] | None] = [None] * LOBBY_UI_SLOT_COUNT
        self._kick_menu_offset: dict[str, float] = dict(config.kick_menu_offset)
        self._flow_step = 0
        self._calibrating = False

        existing = list(config.slot_regions)
        for i, region in enumerate(existing[:LOBBY_UI_SLOT_COUNT]):
            if region.get("x") is not None and region.get("y") is not None:
                self._slot_regions[i] = dict(region)

        ctk.CTkLabel(
            self,
            text=(
                "固定校准流程：\n"
                "1) 拖动准星到 1 号槽 → 自动切到 SC2 并右键\n"
                "2) 拖动到「移出房间」→ 确定菜单偏移\n"
                "3) 依次拖动确认 2~10 号槽位置"
            ),
            justify="left",
            wraplength=480,
        ).pack(padx=12, pady=(12, 8), anchor="w")

        host_frame = ctk.CTkFrame(self)
        host_frame.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(host_frame, text="本机句柄").pack(side="left", padx=6)
        self._host_entry = ctk.CTkEntry(host_frame, width=220)
        self._host_entry.insert(0, config.host_handle)
        self._host_entry.pack(side="left", padx=6)

        self._status = ctk.CTkLabel(self, text="点击「开始校准」", justify="left")
        self._status.pack(padx=12, pady=8, anchor="w")

        self._progress_box = ctk.CTkTextbox(self, height=220)
        self._progress_box.pack(fill="both", expand=True, padx=12, pady=6)
        self._refresh_progress()

        btn_row = ctk.CTkFrame(self)
        btn_row.pack(fill="x", padx=12, pady=10)
        ctk.CTkButton(
            btn_row,
            text="开始校准",
            fg_color="#2d6a4f",
            command=self._start_flow,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            btn_row, text="测试识别", width=80, command=self._test_recognition
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            btn_row,
            text="保存并应用",
            command=self._save,
        ).pack(side="right", padx=4)

    def _log(self, line: str) -> None:
        self._status.configure(text=line)
        self._refresh_progress()

    def _refresh_progress(self) -> None:
        lines = ["--- 槽位坐标 ---"]
        for i, region in enumerate(self._slot_regions):
            if region:
                lines.append(
                    f"  槽{i + 1}: x={region['x']:.6f}  y={region['y']:.6f}"
                )
            else:
                lines.append(f"  槽{i + 1}: (未设置)")
        if self._kick_menu_offset:
            lines.append(
                f"--- 菜单偏移 ---"
                f" dx={self._kick_menu_offset.get('dx', 0):.6f}"
                f" dy={self._kick_menu_offset.get('dy', 0):.6f}"
            )
        self._progress_box.delete("1.0", "end")
        self._progress_box.insert("end", "\n".join(lines))

    def _start_flow(self) -> None:
        if self._calibrating:
            return
        self._calibrating = True
        self._flow_step = 0
        self._log("步骤 1/11：拖动到 1 号槽")
        self._drag_slot1()

    def _on_drag_cancel(self) -> None:
        self._calibrating = False
        self._log("校准已取消")

    def _run_drag(self, instruction: str, on_done) -> None:
        try:
            run_drag_mark(
                self,
                instruction,
                on_done,
                window_title=self._config.window_title_contains,
                on_cancel=self._on_drag_cancel,
            )
        except Exception as exc:
            self._calibrating = False
            self._log(f"无法打开校准层: {exc}")
            from tkinter import messagebox

            messagebox.showerror(
                "UI 校准",
                f"无法启动拖动校准:\n{exc}\n\n请重试或查看日志。",
                parent=self,
            )

    def _drag_slot1(self) -> None:
        self._run_drag(
            "步骤 1/11：拖动绿色准星到 1 号槽玩家行，松开后将自动在 SC2 中右键",
            self._on_slot1_marked,
        )

    def _on_slot1_marked(self, screen_x: int, screen_y: int) -> None:
        region = screen_point_to_slot_region(
            screen_x, screen_y, self._config.window_title_contains
        )
        if region is None:
            self._calibrating = False
            self._log("1 号槽坐标无效（请在 SC2 窗口范围内标记）")
            return
        self._slot_regions[0] = region
        self._refresh_progress()
        self._log("正在切到 SC2 并右键 1 号槽…")

        def work() -> None:
            from antismurf.actions.kick_script import sc2_right_click_screen

            sc2_right_click_screen(self._config, screen_x, screen_y)
            self.after(0, self._drag_menu)

        threading.Thread(target=work, daemon=True).start()

    def _drag_menu(self) -> None:
        self._log("步骤 2/11：拖动到「移出房间」菜单项")
        self._run_drag(
            "步骤 2/11：SC2 菜单已打开，拖动准星到「移出房间」行并松开",
            self._on_menu_marked,
        )

    def _on_menu_marked(self, screen_x: int, screen_y: int) -> None:
        slot1 = self._slot_regions[0]
        menu = screen_point_to_slot_region(
            screen_x, screen_y, self._config.window_title_contains
        )
        if slot1 is None or menu is None:
            self._calibrating = False
            self._log("菜单坐标无效")
            return
        result = apply_manual_menu_offset(slot1, menu)
        if result.ok and result.menu_offset:
            self._kick_menu_offset = dict(result.menu_offset)
            self._config.kick_menu_offset = dict(result.menu_offset)
            if result.menu_click:
                self._config.kick_menu_remove_region = dict(result.menu_click)
        self._flow_step = 2
        self._refresh_progress()
        self._drag_next_slot(1)

    def _drag_next_slot(self, index: int) -> None:
        if index >= LOBBY_UI_SLOT_COUNT:
            self._calibrating = False
            self._log("校准完成，请保存并测试踢人")
            return
        ui = index + 1
        self._log(f"步骤 {index + 2}/11：拖动到 {ui} 号槽")
        self._run_drag(
            f"步骤 {index + 2}/11：拖动准星到 {ui} 号槽玩家行并松开",
            lambda sx, sy, idx=index: self._on_slot_marked(idx, sx, sy),
        )

    def _on_slot_marked(self, index: int, screen_x: int, screen_y: int) -> None:
        region = screen_point_to_slot_region(
            screen_x, screen_y, self._config.window_title_contains
        )
        if region is None:
            self._calibrating = False
            self._log(f"槽位 {index + 1} 坐标无效")
            return
        self._slot_regions[index] = region
        self._refresh_progress()
        self._drag_next_slot(index + 1)

    def _test_recognition(self) -> None:
        if self._orchestrator:
            preview = self._orchestrator.preview_recognition()
        else:
            from antismurf.vision.lobby_reader import LobbyReader

            reader = LobbyReader(self._config)
            preview = reader.preview()

        lines = [
            f"SC2 窗口: {'已找到' if preview.get('window_found') else '未找到'}",
            f"阶段: {preview.get('roster_phase', 'unknown')}",
            f"在房间: {'是' if preview.get('roster_in_room') else '否'}",
            f"主机句柄: {preview.get('local_handle') or '(未读取)'}",
            f"成员: {preview.get('roster_member_count', 0)}",
            f"基址: {preview.get('roster_base') or '-'}",
        ]
        if preview.get("error"):
            lines.append(f"提示: {preview['error']}")
        for slot in preview.get("slots", []):
            lines.append(
                f"  [{slot.get('index', 0) + 1}] "
                f"{slot.get('display_name') or ''} {slot.get('handle') or ''}"
            )
        self._progress_box.delete("1.0", "end")
        self._progress_box.insert("end", "\n".join(lines))

    def _save(self) -> None:
        regions = [r for r in self._slot_regions if r is not None]
        if not regions:
            self._log("请至少完成 1 号槽校准")
            return
        self._config.host_handle = self._host_entry.get().strip()
        self._config.slot_regions = [
            r if r is not None else {"x": 0.5, "y": 0.5}
            for r in self._slot_regions
        ]
        self._config.kick_menu_offset = dict(self._kick_menu_offset)
        if self._slot_regions[0] and self._kick_menu_offset:
            from antismurf.actions.kick_calibration import menu_click_from_slot

            self._config.kick_menu_remove_region = menu_click_from_slot(
                self._slot_regions[0], self._kick_menu_offset
            )
        if len(self._slot_regions) >= 2 and self._slot_regions[0] and self._slot_regions[1]:
            step = normalized_offset(
                (self._slot_regions[0]["x"], self._slot_regions[0]["y"]),
                (self._slot_regions[1]["x"], self._slot_regions[1]["y"]),
            )
            self._config.kick_slot_step = step
        path = save_user_calibration(self._config)
        if self._on_saved:
            self._on_saved(self._config)
        self._log(f"已保存到 {path.name}")
