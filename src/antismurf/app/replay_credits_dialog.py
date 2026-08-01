"""Replay upload + 194823 credits / redemption command hub."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from tkinter import filedialog
from typing import TYPE_CHECKING, Callable

import customtkinter as ctk

from antismurf.community.ks2_credits import Ks2CreditsInfo, fetch_ks2_credits
from antismurf.config.settings import AppConfig, save_user_config
from antismurf.replay.paths import resolve_replay_upload_paths
from antismurf.utils.clipboard import copy_to_clipboard

if TYPE_CHECKING:
    from antismurf.app.orchestrator import Orchestrator


class ReplayCreditsDialog(ctk.CTkToplevel):
    """Upload KS2 replays and query 194823 redemption commands."""

    def __init__(
        self,
        parent: ctk.CTk,
        config: AppConfig,
        *,
        orchestrator: Orchestrator | None = None,
        loop: asyncio.AbstractEventLoop | None = None,
        on_saved: Callable[[AppConfig], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.title("录像上传与积分兑奖")
        self.geometry("640x520")
        self._config = config
        self._orchestrator = orchestrator
        self._loop = loop
        self._on_saved = on_saved
        self._busy = False

        scroll = ctk.CTkScrollableFrame(self, label_text="194823 工具站 · 录像与积分")
        scroll.pack(fill="both", expand=True, padx=10, pady=10)

        self._status = ctk.CTkLabel(scroll, text="", anchor="w", text_color="#b08900")
        self._status.pack(fill="x", pady=(0, 8))

        self._handle_label = ctk.CTkLabel(
            scroll,
            text="主机句柄: （未检测到）",
            anchor="w",
            wraplength=580,
        )
        self._handle_label.pack(fill="x", padx=4, pady=(0, 6))

        self._replay_path = self._add_path_row(
            scroll,
            "录像目录",
            config.replays_paths[0] if config.replays_paths else "",
            is_dir=True,
        )
        self._paths_hint = ctk.CTkLabel(
            scroll,
            text="",
            anchor="w",
            wraplength=580,
            text_color="#9cdcfe",
        )
        self._paths_hint.pack(fill="x", padx=4, pady=(0, 6))

        self._upload_info = ctk.CTkLabel(
            scroll,
            text="",
            anchor="w",
            wraplength=580,
            justify="left",
        )
        self._upload_info.pack(fill="x", padx=4, pady=(0, 8))

        ctk.CTkLabel(scroll, text="积分与兑奖指令", anchor="w").pack(
            fill="x", padx=4, pady=(4, 2)
        )
        self._credits_label = ctk.CTkLabel(
            scroll,
            text="尚未查询",
            anchor="w",
            wraplength=580,
            justify="left",
        )
        self._credits_label.pack(fill="x", padx=4, pady=(0, 4))

        self._code_box = ctk.CTkTextbox(scroll, height=72)
        self._code_box.pack(fill="x", padx=4, pady=(0, 8))
        self._code_box.configure(state="disabled")

        self._rules_path = self._add_path_row(
            scroll,
            "规则包（可选）",
            config.rules_pack_path,
        )

        ctk.CTkLabel(
            scroll,
            text="留空录像目录时，将按主机句柄自动搜索 Documents/StarCraft II/Accounts/…/Replays/Multiplayer。",
            anchor="w",
            wraplength=580,
            text_color="#888888",
        ).pack(fill="x", padx=4, pady=(4, 6))

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=12)
        ctk.CTkButton(
            btn_row,
            text="查询兑奖指令",
            width=120,
            fg_color="#2d6a4f",
            command=self._query_credits,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            btn_row,
            text="立即上传录像",
            width=120,
            command=self._upload_now,
        ).pack(side="left", padx=4)
        ctk.CTkButton(btn_row, text="刷新路径", width=90, command=self._refresh_paths).pack(
            side="left", padx=4
        )
        ctk.CTkButton(
            btn_row,
            text="确认并启用",
            width=110,
            fg_color="#1f538d",
            command=self._confirm,
        ).pack(side="right", padx=4)
        ctk.CTkButton(btn_row, text="保存草稿", width=90, command=self._save_draft).pack(
            side="right", padx=4
        )

        self._refresh_paths()
        self._refresh_upload_status()

    def _local_handle(self) -> str:
        if self._orchestrator is not None:
            handle = self._orchestrator._local_handle or self._config.host_handle
            if handle:
                return handle.strip()
        return self._config.host_handle.strip()

    def _add_path_row(
        self,
        parent: ctk.CTkFrame,
        label: str,
        value: str,
        *,
        is_dir: bool = False,
    ) -> ctk.CTkEntry:
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=4)
        ctk.CTkLabel(row, text=label, width=120, anchor="w").pack(side="left")
        entry = ctk.CTkEntry(row, width=360)
        entry.insert(0, value)
        entry.pack(side="left", padx=6)

        def browse() -> None:
            if is_dir:
                path = filedialog.askdirectory(parent=self, title=label)
            else:
                path = filedialog.askopenfilename(
                    parent=self,
                    title=label,
                    filetypes=[("规则", "*.txt *.toml"), ("所有文件", "*.*")],
                )
            if path:
                entry.delete(0, "end")
                entry.insert(0, path)

        ctk.CTkButton(row, text="浏览", width=60, command=browse).pack(side="left")
        return entry

    def _refresh_paths(self) -> None:
        handle = self._local_handle()
        if handle:
            self._handle_label.configure(text=f"主机句柄: {handle}")
        else:
            self._handle_label.configure(
                text="主机句柄: （未检测到，请在 SC2 房间中运行或使用设置中的 host.handle）"
            )

        discovered = resolve_replay_upload_paths(
            self._config.replays_paths,
            handle or None,
        )
        if discovered:
            hint = "已定位录像目录:\n" + "\n".join(f"  • {path}" for path in discovered[:4])
            if len(discovered) > 4:
                hint += f"\n  … 共 {len(discovered)} 个"
            self._paths_hint.configure(text=hint)
            if not self._replay_path.get().strip():
                self._replay_path.delete(0, "end")
                self._replay_path.insert(0, discovered[0])
        else:
            self._paths_hint.configure(text="未找到录像目录，请手动选择或确认 SC2 已保存过录像。")

    def _refresh_upload_status(self) -> None:
        if self._orchestrator is None:
            self._upload_info.configure(text="后台未启动，无法预览上传状态。")
            return
        preview = self._orchestrator.refresh_replays_sync()
        latest = preview.get("latest_candidate")
        lines = [
            f"自动上传: {'开启' if preview.get('enabled') else '关闭'}",
            f"48h 窗口内待上传: {preview.get('pending_in_window', 0)} 个",
            f"已上传记录: {preview.get('uploaded_count', 0)} 个",
        ]
        if latest:
            lines.append(f"最新候选: {latest}")
        self._upload_info.configure(text="\n".join(lines))

    def _apply_form_to_config(self, *, confirmed: bool) -> AppConfig:
        cfg = self._config
        replay_dir = self._replay_path.get().strip()
        cfg.replays_paths = [replay_dir] if replay_dir else []
        cfg.rules_pack_path = self._rules_path.get().strip()
        if confirmed:
            cfg.data_sources_confirmed = True
        return cfg

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self._busy = busy
        if message:
            self._status.configure(text=message, text_color="#b08900" if busy else "#2d6a4f")

    def _run_async(self, coro, *, on_ok, on_err) -> None:
        if self._loop is None:
            on_err(RuntimeError("后台事件循环未就绪"))
            return

        def _done(future) -> None:
            try:
                result = future.result()
            except Exception as exc:
                self.after(0, lambda: on_err(exc))
            else:
                self.after(0, lambda: on_ok(result))

        asyncio.run_coroutine_threadsafe(coro, self._loop).add_done_callback(_done)

    def _query_credits(self) -> None:
        if self._busy:
            return
        handle = self._local_handle()
        if not handle:
            self._status.configure(text="无法查询：未检测到主机句柄", text_color="#d00000")
            return

        self._set_busy(True, "正在查询积分与兑奖指令…")

        def work() -> Ks2CreditsInfo:
            return fetch_ks2_credits(
                handle,
                timeout_sec=self._config.community_timeout_sec,
            )

        threading.Thread(
            target=lambda: self._finish_credits_query(work),
            daemon=True,
        ).start()

    def _finish_credits_query(self, work) -> None:
        try:
            info = work()
        except Exception as exc:
            self.after(0, lambda: self._on_credits_error(exc))
            return
        self.after(0, lambda: self._on_credits_ok(info))

    def _on_credits_ok(self, info: Ks2CreditsInfo) -> None:
        self._set_busy(False)
        copied = copy_to_clipboard(info.redemption_code)
        self._credits_label.configure(
            text=(
                f"上传积分: {info.replay_credits}  ·  罚分: {info.penalty}  ·  "
                f"可用: {info.net_credits}"
            )
        )
        self._code_box.configure(state="normal")
        self._code_box.delete("1.0", "end")
        self._code_box.insert("1.0", info.redemption_code)
        self._code_box.configure(state="disabled")
        copy_msg = "已复制兑奖指令到剪贴板" if copied else "兑奖指令复制失败，请手动复制"
        self._status.configure(
            text=f"查询成功 · {copy_msg}",
            text_color="#2d6a4f",
        )

    def _on_credits_error(self, exc: Exception) -> None:
        self._set_busy(False)
        self._status.configure(text=f"查询失败: {exc}", text_color="#d00000")

    def _upload_now(self) -> None:
        if self._busy:
            return
        if self._orchestrator is None:
            self._status.configure(text="后台未启动", text_color="#d00000")
            return
        cfg = self._apply_form_to_config(confirmed=False)
        self._config = cfg
        if self._on_saved:
            self._on_saved(cfg)
        self._set_busy(True, "正在上传录像…")

        def work() -> list[dict]:
            return self._orchestrator.upload_replays_now_sync()

        threading.Thread(
            target=lambda: self._finish_upload(work),
            daemon=True,
        ).start()

    def _finish_upload(self, work) -> None:
        try:
            results = work()
        except Exception as exc:
            self.after(0, lambda: self._on_upload_error(exc))
            return
        self.after(0, lambda: self._on_upload_ok(results))

    def _on_upload_ok(self, results: list[dict]) -> None:
        self._set_busy(False)
        self._refresh_upload_status()
        if not results:
            self._status.configure(text="没有可上传的录像", text_color="#b08900")
            return
        ok_names = [item["name"] for item in results if item.get("ok")]
        failed = [item for item in results if not item.get("ok")]
        if ok_names:
            msg = f"已上传 {len(ok_names)} 个: " + ", ".join(ok_names[:3])
            if len(ok_names) > 3:
                msg += " …"
            color = "#2d6a4f"
        else:
            msg = "上传未完成"
            color = "#d00000"
        if failed:
            msg += f"（失败 {len(failed)} 个: {failed[0].get('error', '?')}）"
        self._status.configure(text=msg, text_color=color)

    def _on_upload_error(self, exc: Exception) -> None:
        self._set_busy(False)
        self._status.configure(text=f"上传失败: {exc}", text_color="#d00000")

    def _save_draft(self) -> None:
        cfg = self._apply_form_to_config(confirmed=False)
        save_user_config(cfg)
        self._config = cfg
        if self._on_saved:
            self._on_saved(cfg)
        self._status.configure(text="草稿已保存", text_color="#b08900")

    def _confirm(self) -> None:
        replay_dir = self._replay_path.get().strip()
        if replay_dir and not Path(replay_dir).is_dir():
            self._status.configure(text=f"录像目录不存在: {replay_dir}", text_color="#d00000")
            return
        cfg = self._apply_form_to_config(confirmed=True)
        rule_err: str | None = None
        if cfg.rules_pack_path and self._orchestrator:
            rule_err = self._orchestrator.reload_rules_pack()
        save_user_config(cfg)
        self._config = cfg
        if self._on_saved:
            self._on_saved(cfg)
        msg = "已确认并启用"
        if rule_err:
            msg += f"（规则包: {rule_err}）"
        self._status.configure(text=msg, text_color="#2d6a4f")
        if self._orchestrator and self._config.replay_upload_enabled:
            self._upload_now()
