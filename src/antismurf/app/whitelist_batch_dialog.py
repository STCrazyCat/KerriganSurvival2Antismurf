"""Batch whitelist dialog: paste many handles, auto-complete, validate."""

from __future__ import annotations

import asyncio
from typing import Any, Callable

import customtkinter as ctk

from antismurf.models.player import parse_handle_batch

HELP_TEXT = (
    "粘贴多个句柄,分隔符自动识别(空格 / 逗号 / 分号 / 顿号 / 换行)。\n"
    "只输入数字时会自动补全句柄开头 5-S2-1-(例如 1234567 → 5-S2-1-1234567)。\n"
    "非法内容会在解析结果中列出,不会添加。"
)


class WhitelistBatchDialog(ctk.CTkToplevel):
    def __init__(
        self,
        parent: ctk.CTk,
        orchestrator: Any,
        loop: asyncio.AbstractEventLoop,
        on_log: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.title("批量添加白名单")
        self.geometry("640x560")
        self._orchestrator = orchestrator
        self._loop = loop
        self._on_log = on_log
        self._valid: list[str] = []
        self._invalid: list[str] = []

        ctk.CTkLabel(
            self, text=HELP_TEXT, anchor="w", justify="left", wraplength=600
        ).pack(fill="x", padx=12, pady=(12, 4))

        self._input = ctk.CTkTextbox(self, height=180)
        self._input.pack(fill="x", padx=12, pady=6)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=4)
        ctk.CTkButton(btn_row, text="解析", width=80, command=self._parse).pack(
            side="left"
        )
        self._add_btn = ctk.CTkButton(
            btn_row,
            text="添加到白名单",
            width=120,
            fg_color="#2d6a4f",
            command=self._add,
            state="disabled",
        )
        self._add_btn.pack(side="left", padx=8)
        ctk.CTkButton(btn_row, text="关闭", command=self.destroy).pack(side="right")

        ctk.CTkLabel(self, text="解析结果:", anchor="w").pack(
            fill="x", padx=12, pady=(8, 0)
        )
        self._result = ctk.CTkTextbox(self, height=220, state="disabled")
        self._result.pack(fill="both", expand=True, padx=12, pady=(4, 12))

    def _parse(self) -> None:
        text = self._input.get("1.0", "end")
        self._valid, self._invalid = parse_handle_batch(text)
        self._render_result()
        self._add_btn.configure(state="normal" if self._valid else "disabled")

    def _render_result(self) -> None:
        lines: list[str] = []
        lines.append(f"有效句柄 {len(self._valid)} 个:")
        for h in self._valid:
            lines.append(f"  ✓ {h}")
        lines.append(f"无效内容 {len(self._invalid)} 个:")
        for item in self._invalid:
            lines.append(f"  ✗ {item}")
        self._result.configure(state="normal")
        self._result.delete("1.0", "end")
        self._result.insert("1.0", "\n".join(lines))
        self._result.configure(state="disabled")

    def _add(self) -> None:
        if not self._valid:
            return
        handles = list(self._valid)
        self._add_btn.configure(state="disabled", text="添加中…")

        def done(f) -> None:
            try:
                added = f.result()
            except Exception as exc:  # noqa: BLE001
                self.after(0, lambda: self._on_done(f"添加失败: {exc}"))
                return
            self.after(0, lambda: self._on_done(f"已新增 {added} 个白名单句柄"))

        future = asyncio.run_coroutine_threadsafe(
            self._orchestrator.whitelist_handles(handles), self._loop
        )
        future.add_done_callback(done)

    def _on_done(self, message: str) -> None:
        self._add_btn.configure(state="normal", text="添加到白名单")
        self._append_result(message + "\n")
        if self._on_log:
            self._on_log(message)

    def _append_result(self, text: str) -> None:
        self._result.configure(state="normal")
        self._result.insert("end", text)
        self._result.configure(state="disabled")
