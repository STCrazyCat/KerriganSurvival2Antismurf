from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import TYPE_CHECKING

import customtkinter as ctk

from antismurf.build_meta import (
    APP_DISPLAY_NAME,
    AUTO_KICK_ENABLED,
    BUILD_VERSION,
    MEMORY_SCAN_AVAILABLE,
)
from antismurf.config.settings import AppConfig, apply_memory_runtime_defaults, load_config
from antismurf.features import memory_scan_available
from antismurf.lobby.sc2_process import Sc2WindowInfo, list_sc2_windows
from antismurf.models.evaluation import PlayerRecord
from antismurf.config.kick_defaults import ui_slot_label
from antismurf.app.mmr_display import faction_stats_for_record
from antismurf.app.score_theme import score_color
from antismurf.review.profile_assist import ProfileAssist

if TYPE_CHECKING:
    from antismurf.app.orchestrator import Orchestrator

logger = logging.getLogger(__name__)

TIER_COLORS = {
    "low": "#2d6a4f",
    "medium": "#b08900",
    "high": "#d00000",
    "critical": "#9d0208",
}

TIER_LABELS = {
    "low": "低",
    "medium": "中",
    "high": "高",
    "critical": "极高",
}


def suspect_name_color_for(record: PlayerRecord, config: AppConfig) -> str | None:
    """嫌疑提示字体颜色:疑似小号(拉黑标记/高嫌疑)、黑名单、非白名单
    (白名单模式下)的玩家名称着色,否则返回 None。"""
    if record.tier in ("high", "critical"):
        return config.suspect_name_color
    if any(mark.handle == record.handle for mark in config.handle_mark_rules):
        return config.suspect_name_color
    if record.handle in config.blocklist_handles:
        return config.suspect_name_color
    if config.whitelist_mode and not record.whitelisted:
        if not any(
            trust.handle == record.handle for trust in config.handle_trust_rules
        ):
            return config.suspect_name_color
    return None


def _format_handle(record: PlayerRecord) -> str:
    if record.remark:
        return f"{record.handle} ({record.remark})"
    return record.handle


def _format_player_id(record: PlayerRecord) -> str:
    if record.display_name:
        return record.display_name
    if record.profile_id is not None:
        return str(record.profile_id)
    if record.discriminator is not None:
        return str(record.discriminator)
    return "-"


def _core_gap(record: PlayerRecord) -> str:
    from antismurf.data.player_display import core_gap_summary

    return core_gap_summary(record)


class AntiSmurfApp(ctk.CTk):
    def __init__(self, config: AppConfig | None = None) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title(
            f"{APP_DISPLAY_NAME} v{BUILD_VERSION} — 凯瑞甘生存2 内存模式6"
            if MEMORY_SCAN_AVAILABLE
            else f"{APP_DISPLAY_NAME} — 凯瑞甘生存2 防炸鱼"
        )
        self.geometry("1280x720")
        self.minsize(860, 560)

        self._config = apply_memory_runtime_defaults(config or load_config())
        self._orchestrator: Orchestrator | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._profile = ProfileAssist(self._config)
        self._player_rows: dict[str, ctk.CTkFrame] = {}
        self._alerted_handles: set[str] = set()
        self._is_local_host: bool = False
        self._sc2_windows: list[Sc2WindowInfo] = []
        self._last_refresh_click_at: float = 0.0
        self._list_only_mode = bool(
            self._config.memory_list_only and memory_scan_available()
        )

        self._build_header()
        self._build_sc2_process_bar()
        self._build_player_list()
        self._build_log()
        self._start_backend()

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self)
        header.pack(fill="x", padx=10, pady=(10, 4))

        # 功能按钮行：按钮优先完整显示；窗口过窄放不下时，
        # 通过底部横向滑动条访问全部按钮（Shift+滚轮或拖动滚动条）。
        btn_bar = ctk.CTkScrollableFrame(
            header,
            orientation="horizontal",
            height=44,
            corner_radius=0,
            fg_color="transparent",
        )
        btn_bar.pack(fill="x")

        if MEMORY_SCAN_AVAILABLE:
            ctk.CTkLabel(
                btn_bar,
                text=f"构建 {BUILD_VERSION}",
                text_color="#888888",
            ).pack(side="right", padx=(4, 10))

        ctk.CTkButton(
            btn_bar, text="说明", width=60, command=self._open_help
        ).pack(side="right", padx=6)

        ctk.CTkButton(
            btn_bar, text="录像与积分", width=90, command=self._open_replay_credits
        ).pack(side="right", padx=6)

        ctk.CTkButton(
            btn_bar, text="UI 校准", width=80, command=self._open_calibration
        ).pack(side="right", padx=6)

        ctk.CTkButton(
            btn_bar, text="评分规则", width=80, command=self._open_rule_editor
        ).pack(side="right", padx=6)

        ctk.CTkButton(
            btn_bar, text="识别历史", width=80, command=self._open_player_history
        ).pack(side="right", padx=6)

        ctk.CTkButton(
            btn_bar, text="活动日志", width=80, command=self._open_activity_log
        ).pack(side="right", padx=6)

        ctk.CTkButton(
            btn_bar, text="设置", width=60, command=self._open_settings
        ).pack(side="right", padx=6)

        ctk.CTkButton(
            btn_bar, text="刷新", width=60, command=self._manual_refresh
        ).pack(side="right", padx=6)

        self._dry_run_var = ctk.BooleanVar(value=self._config.dry_run)
        ctk.CTkCheckBox(
            btn_bar,
            text="Dry Run（不实际踢人）",
            variable=self._dry_run_var,
            command=self._on_toggle_dry_run,
        ).pack(side="right", padx=10)

        self._auto_kick_var = ctk.BooleanVar(value=self._config.auto_kick_enabled)
        self._auto_kick_checkbox: ctk.CTkCheckBox | None = None
        if AUTO_KICK_ENABLED:
            self._auto_kick_checkbox = ctk.CTkCheckBox(
                btn_bar,
                text="极高嫌疑自动踢",
                variable=self._auto_kick_var,
                command=self._on_toggle_auto_kick,
            )
            self._auto_kick_checkbox.pack(side="right", padx=10)

        self._whitelist_mode_var = ctk.BooleanVar(value=self._config.whitelist_mode)
        ctk.CTkCheckBox(
            btn_bar,
            text="白名单模式",
            variable=self._whitelist_mode_var,
            command=self._on_toggle_whitelist_mode,
        ).pack(side="right", padx=10)

        ctk.CTkButton(
            btn_bar,
            text="批量白名单",
            width=90,
            command=self._open_whitelist_batch,
        ).pack(side="right", padx=6)

        # 状态文本行：固定高度，长文本自动换行，可通过纵向滑动条查看全部内容
        self._status_box = ctk.CTkTextbox(
            header,
            height=64,
            wrap="word",
            font=ctk.CTkFont(size=13),
        )
        self._status_box.pack(fill="x", pady=(6, 0))
        self._set_status("状态: 等待 SC2 房间（模式6 自动检测）")

    def _set_status(self, text: str) -> None:
        self._status_box.configure(state="normal")
        self._status_box.delete("1.0", "end")
        self._status_box.insert("1.0", text)
        self._status_box.configure(state="disabled")

    def _build_sc2_process_bar(self) -> None:
        bar = ctk.CTkFrame(self)
        bar.pack(fill="x", padx=10, pady=(0, 4))
        self._sc2_process_bar = bar

        ctk.CTkLabel(bar, text="SC2 进程", width=70, anchor="w").pack(
            side="left", padx=(6, 4)
        )
        self._sc2_process_var = ctk.StringVar(value="自动（首个 SC2 进程）")
        self._sc2_process_menu = ctk.CTkComboBox(
            bar,
            variable=self._sc2_process_var,
            values=["自动（首个 SC2 进程）"],
            width=520,
            state="readonly",
            command=self._on_sc2_process_selected,
        )
        self._sc2_process_menu.pack(side="left", padx=4)

        ctk.CTkButton(
            bar,
            text="刷新",
            width=70,
            command=self._refresh_sc2_windows,
        ).pack(side="left", padx=4)

        if not memory_scan_available():
            bar.pack_forget()

    def _refresh_sc2_windows(self) -> None:
        self._sc2_windows = list_sc2_windows(self._config.memory_process_names)
        labels = ["自动（首个 SC2 进程）"]
        labels.extend(item.label for item in self._sc2_windows)
        if len(labels) == 1:
            labels = ["自动（首个 SC2 进程）", "未检测到 SC2 进程 — 请先启动游戏"]
        self._sc2_process_menu.configure(values=labels)

        current_pid = self._config.memory_target_pid
        selected = labels[0]
        if current_pid:
            for item in self._sc2_windows:
                if item.pid == current_pid:
                    selected = item.label
                    break
        self._sc2_process_var.set(selected)

        if len(self._sc2_windows) == 1:
            self._apply_sc2_target_pid(self._sc2_windows[0].pid)
        elif not self._sc2_windows:
            self._apply_sc2_target_pid(0)
            self._log("未找到 SC2 进程，请启动 StarCraft II 后点击刷新。")
        else:
            self._log(f"已刷新 SC2 进程列表，共 {len(self._sc2_windows)} 个。")

    def _on_sc2_process_selected(self, choice: str) -> None:
        if choice.startswith("自动"):
            self._apply_sc2_target_pid(0)
            return
        if choice.startswith("未检测到"):
            return
        for item in self._sc2_windows:
            if item.label == choice:
                self._apply_sc2_target_pid(item.pid)
                return

    def _apply_sc2_target_pid(self, pid: int) -> None:
        self._config.memory_target_pid = int(pid or 0)
        if self._orchestrator is not None:
            self._orchestrator.set_sc2_target_pid(pid or None)
        if pid:
            self._log(f"已选择 SC2 进程 PID {pid}")
        else:
            self._log("SC2 进程选择：自动（首个进程）")

    def _build_player_list(self) -> None:
        label = (
            "大厅玩家（句柄 / 战队 / 昵称 / 分阵营 MMR 与 playlike）"
            " — MMR：核心·差值(核心−平均PL)；PL：均值·前三"
            if self._list_only_mode
            else "大厅玩家"
        )
        container = ctk.CTkScrollableFrame(self, label_text=label)
        container.pack(fill="both", expand=True, padx=10, pady=5)
        self._list_frame = container

        cols = ctk.CTkFrame(container)
        cols.pack(fill="x", pady=(0, 5))
        if self._list_only_mode:
            column_defs = [
                ("句柄", 150),
                ("战队", 80),
                ("昵称", 100),
                ("幸存MMR", 168),
                ("幸存PL", 128),
                ("凯瑞甘MMR", 168),
                ("凯瑞甘PL", 128),
                ("分", 36),
                ("槽位", 36),
                ("操作", 56),
            ]
        else:
            column_defs = [
                ("句柄", 160),
                ("玩家ID", 100),
                ("MMR", 70),
                ("Playlike", 70),
                ("核心差", 60),
                ("嫌疑", 50),
                ("分数", 50),
                ("规则", 180),
                ("操作", 500),
            ]
        for text, width in column_defs:
            ctk.CTkLabel(cols, text=text, width=width, anchor="w").pack(
                side="left", padx=2
            )

    def _build_log(self) -> None:
        self._log_box = ctk.CTkTextbox(self, height=120)
        self._log_box.pack(fill="x", padx=10, pady=10)

    def _log(self, msg: str) -> None:
        self._log_box.insert("end", msg + "\n")
        self._log_box.see("end")

    def _start_backend(self) -> None:
        from antismurf.app.orchestrator import Orchestrator

        def run_loop() -> None:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._orchestrator = Orchestrator(
                self._config, on_update=self._on_players_update
            )
            self._loop.run_until_complete(self._orchestrator.start())
            self._loop.run_forever()

        self._thread = threading.Thread(target=run_loop, daemon=True)
        self._thread.start()
        self._log(f"后台监控已启动（{BUILD_VERSION}，辅助工具模式6）")
        if memory_scan_available():
            self.after(300, self._refresh_sc2_windows)

    def _on_players_update(
        self,
        players: dict[str, PlayerRecord],
        active: bool,
        map_name: str | None,
        is_local_host: bool,
        vision_paused: bool = False,
        manual_lobby: bool = False,
    ) -> None:
        self.after(
            0,
            lambda: self._refresh_ui(
                players, active, map_name, is_local_host, vision_paused, manual_lobby
            ),
        )

    def _refresh_ui(
        self,
        players: dict[str, PlayerRecord],
        active: bool,
        map_name: str | None,
        is_local_host: bool,
        _vision_paused: bool = False,
        _manual_lobby: bool = False,
    ) -> None:
        self._is_local_host = is_local_host
        kick_state = "normal" if is_local_host else "disabled"
        if self._auto_kick_checkbox is not None:
            self._auto_kick_checkbox.configure(state=kick_state)
        if active:
            role = "房主" if is_local_host else "非房主"
            status = (
                f"状态: KS2 房间运行中（{role}，模式6）— "
                f"{map_name or '凯瑞甘生存2'}"
            )
            self._set_status(status)
        else:
            status = self._format_idle_status()
            self._set_status(status)

        seen = set()
        for handle, record in players.items():
            seen.add(handle)
            if handle not in self._player_rows:
                self._player_rows[handle] = self._create_row(record)
            else:
                self._update_row(record)

        for handle in list(self._player_rows):
            if handle not in seen:
                self._player_rows[handle].destroy()
                del self._player_rows[handle]

        for handle, row in self._player_rows.items():
            kick_btn = getattr(row, "_kick_btn", None)
            if kick_btn is not None:
                kick_btn.configure(state=kick_state)

        for handle, record in players.items():
            if (
                record.tier in ("high", "critical")
                and not record.whitelisted
                and handle not in self._alerted_handles
            ):
                self._alerted_handles.add(handle)
                self._log(
                    f"⚠ 高嫌疑玩家: {handle} ({TIER_LABELS[record.tier]})"
                )

    def _format_idle_status(self) -> str:
        if self._orchestrator is None:
            return "状态: 等待 SC2 房间（模式6 自动检测）"
        roster = self._orchestrator.last_roster_status
        err = self._orchestrator.last_scan_error
        phase = roster.get("phase", "unknown")
        in_room = roster.get("in_room")
        members = roster.get("member_count", 0)
        base = roster.get("record_base")
        parts = ["状态: 等待 KS2 房间"]
        if in_room:
            parts[0] = "状态: KS2 房间"
            parts.append(f"成员={members}")
        elif phase == "out_of_room":
            parts.append("未在房间")
        if base:
            parts.append(f"基址=0x{int(base):X}")
        # 句柄位置确认状态:是否抓到房间内玩家句柄
        loc_state = roster.get("handle_location_state", "unknown")
        loc_source = roster.get("handle_location_source", "none")
        if loc_state == "confirmed":
            if loc_source == "roster":
                parts.append("句柄位置=已确认(roster)")
            else:
                addr = roster.get("host_handle_address")
                addr_text = f"@0x{int(addr):X}" if addr else ""
                parts.append(f"句柄位置=已确认({loc_source}){addr_text}")
        else:
            parts.append("句柄位置=未确认")
        if roster.get("roster_verified") and in_room:
            parts.append("玩家句柄=已抓到")
        if err:
            parts.append(f"提示={err}")
        return " | ".join(parts)

    def _create_row(self, record: PlayerRecord) -> ctk.CTkFrame:
        if self._list_only_mode:
            return self._create_list_only_row(record)
        row = ctk.CTkFrame(self._list_frame)
        row.pack(fill="x", pady=2)

        labels: dict[str, ctk.CTkLabel] = {}
        mmr = record.community.mmr if record.community else None
        pl = record.community.mmr_playlike if record.community else None

        for key, text, width in [
            ("handle", _format_handle(record), 160),
            ("profile_id", _format_player_id(record), 100),
            ("mmr", f"{mmr:.0f}" if mmr else "-", 70),
            ("pl", f"{pl:.0f}" if pl else "-", 70),
            ("gap", _core_gap(record), 60),
            ("tier", TIER_LABELS.get(record.tier, record.tier), 50),
            ("score", f"{record.score:.0f}", 50),
            ("rules", ", ".join(record.triggered_rules[:3]) or "-", 180),
        ]:
            lbl = ctk.CTkLabel(row, text=text, width=width, anchor="w")
            lbl.pack(side="left", padx=2)
            labels[key] = lbl

        btn_frame = ctk.CTkFrame(row, fg_color="transparent")
        btn_frame.pack(side="left", padx=2)
        kick_state = "normal" if self._is_local_host else "disabled"

        ctk.CTkButton(
            btn_frame,
            text="详情",
            width=60,
            command=lambda h=record.handle: self._open_detail(h),
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            btn_frame,
            text="档案",
            width=60,
            command=lambda h=record.handle: self._open_profile(h),
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            btn_frame,
            text="战绩",
            width=60,
            command=lambda h=record.handle: self._fetch_history(h),
        ).pack(side="left", padx=2)
        kick_btn = ctk.CTkButton(
            btn_frame,
            text="踢出",
            width=60,
            fg_color="#d00000",
            state=kick_state,
            command=lambda h=record.handle, s=record.slot_index: self._kick(h, s),
        )
        kick_btn.pack(side="left", padx=2)
        row._kick_btn = kick_btn  # type: ignore[attr-defined]
        ctk.CTkButton(
            btn_frame,
            text="拉黑+200",
            width=72,
            fg_color="#8a6d00",
            command=lambda h=record.handle: self._blacklist_mark(h),
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            btn_frame,
            text="白名单",
            width=70,
            command=lambda h=record.handle: self._whitelist(h),
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            btn_frame,
            text="降级",
            width=60,
            command=lambda h=record.handle: self._downgrade(h),
        ).pack(side="left", padx=2)
        ctk.CTkButton(
            btn_frame,
            text="黑名单",
            width=60,
            fg_color="#555",
            command=lambda h=record.handle: self._blocklist(h),
        ).pack(side="left", padx=2)

        row._labels = labels  # type: ignore[attr-defined]
        tier_lbl = labels["tier"]
        tier_lbl.configure(text_color=TIER_COLORS.get(record.tier, "white"))
        labels["score"].configure(text_color=score_color(record.score, self._config))
        name_color = self._suspect_name_color(record)
        if name_color:
            labels["handle"].configure(text_color=name_color)
        return row

    def _create_list_only_row(self, record: PlayerRecord) -> ctk.CTkFrame:
        row = ctk.CTkFrame(self._list_frame)
        row.pack(fill="x", pady=2)
        labels: dict[str, ctk.CTkLabel] = {}
        stats = faction_stats_for_record(record)
        nickname = record.display_name or "-"
        team = record.team_name or "-"
        score_text = f"{record.score:.0f}" if record.score else "-"
        for key, text, width in [
            ("handle", record.handle, 150),
            ("team", team, 80),
            ("nickname", nickname, 100),
            ("s_mmr", stats["s_mmr"], 168),
            ("s_pl", stats["s_pl"], 128),
            ("k_mmr", stats["k_mmr"], 168),
            ("k_pl", stats["k_pl"], 128),
            ("score", score_text, 36),
            ("slot", ui_slot_label(record.slot_index), 36),
        ]:
            lbl = ctk.CTkLabel(
                row,
                text=text,
                width=width,
                anchor="w",
                font=ctk.CTkFont(size=11),
            )
            lbl.pack(side="left", padx=2)
            labels[key] = lbl
        kick_state = "normal" if self._is_local_host else "disabled"
        kick_btn = ctk.CTkButton(
            row,
            text="踢出",
            width=48,
            fg_color="#d00000",
            state=kick_state,
            command=lambda h=record.handle, s=record.slot_index: self._kick(h, s),
        )
        kick_btn.pack(side="left", padx=2)
        row._kick_btn = kick_btn  # type: ignore[attr-defined]
        ctk.CTkButton(
            row,
            text="拉黑",
            width=48,
            fg_color="#8a6d00",
            command=lambda h=record.handle: self._blacklist_mark(h),
        ).pack(side="left", padx=2)
        row._labels = labels  # type: ignore[attr-defined]
        labels["score"].configure(text_color=score_color(record.score, self._config))
        name_color = self._suspect_name_color(record)
        if name_color:
            labels["nickname"].configure(text_color=name_color)
        return row

    def _suspect_name_color(self, record: PlayerRecord) -> str | None:
        return suspect_name_color_for(record, self._config)

    def _update_row(self, record: PlayerRecord) -> None:
        row = self._player_rows.get(record.handle)
        if not row:
            return
        if self._list_only_mode:
            labels = row._labels  # type: ignore[attr-defined]
            stats = faction_stats_for_record(record)
            labels["handle"].configure(text=record.handle)
            labels["team"].configure(text=record.team_name or "-")
            labels["nickname"].configure(text=record.display_name or "-")
            name_color = self._suspect_name_color(record)
            if name_color:
                labels["nickname"].configure(text_color=name_color)
            labels["s_mmr"].configure(text=stats["s_mmr"])
            labels["s_pl"].configure(text=stats["s_pl"])
            labels["k_mmr"].configure(text=stats["k_mmr"])
            labels["k_pl"].configure(text=stats["k_pl"])
            labels["score"].configure(
                text=f"{record.score:.0f}" if record.score else "-",
                text_color=score_color(record.score, self._config),
            )
            labels["slot"].configure(text=ui_slot_label(record.slot_index))
            return
        labels = row._labels  # type: ignore[attr-defined]
        mmr = record.community.mmr if record.community else None
        pl = record.community.mmr_playlike if record.community else None
        labels["handle"].configure(text=_format_handle(record))
        name_color = self._suspect_name_color(record)
        if name_color:
            labels["handle"].configure(text_color=name_color)
        labels["profile_id"].configure(text=_format_player_id(record))
        labels["mmr"].configure(text=f"{mmr:.0f}" if mmr else "-")
        labels["pl"].configure(text=f"{pl:.0f}" if pl else "-")
        labels["gap"].configure(text=_core_gap(record))
        labels["tier"].configure(
            text=TIER_LABELS.get(record.tier, record.tier),
            text_color=TIER_COLORS.get(record.tier, "white"),
        )
        labels["score"].configure(
            text=f"{record.score:.0f}",
            text_color=score_color(record.score, self._config),
        )
        labels["rules"].configure(
            text=", ".join(record.triggered_rules[:3]) or "-"
        )

    def _open_profile(self, handle: str) -> None:
        slot = None
        if self._orchestrator and handle in self._orchestrator.players:
            slot = self._orchestrator.players[handle].slot_index
        if self._profile.open_profile(handle, slot_index=slot):
            self._log(f"已在游戏内打开档案: {handle}")
            self.after(1500, lambda h=handle: self._try_save_profile_ref_from_clipboard(h))
        else:
            self._log(f"打开档案失败: {handle}")

    def _try_save_profile_ref_from_clipboard(self, handle: str) -> None:
        if not self._orchestrator:
            return
        ref = self._profile.try_read_profile_ref_from_clipboard()
        if not ref:
            return
        self._orchestrator.save_profile_ref_sync(
            handle, ref.region_id, ref.realm_id, ref.profile_id
        )
        self._log(f"已从剪贴板保存档案 ID: {handle}")

    def _open_detail(self, handle: str) -> None:
        from antismurf.app.player_detail_dialog import PlayerDetailDialog

        if not self._orchestrator or handle not in self._orchestrator.players:
            self._log(f"未找到玩家: {handle}")
            return
        PlayerDetailDialog(self, self._orchestrator.players[handle])

    def _open_activity_log(self) -> None:
        from antismurf.app.activity_log_dialog import ActivityLogDialog

        if not self._orchestrator:
            return
        ActivityLogDialog(self, self._orchestrator)

    def _open_player_history(self) -> None:
        from antismurf.app.player_history_dialog import PlayerHistoryDialog

        if not self._orchestrator:
            return
        PlayerHistoryDialog(
            self,
            orchestrator=self._orchestrator,
            loop=self._loop,
            on_log=self._log,
        )

    def _open_help(self) -> None:
        from antismurf.app.help_dialog import HelpDialog

        HelpDialog(self)

    def _open_rule_editor(self, handle: str | None = None) -> None:
        from antismurf.app.rule_editor_dialog import RuleEditorDialog

        preview_handle = None
        preview_profile = None
        preview_profile_id = None
        preview_history = None
        preview_blocklisted = False
        if handle and self._orchestrator and handle in self._orchestrator.players:
            rec = self._orchestrator.players[handle]
            preview_handle = rec.handle
            preview_profile_id = rec.profile_id or rec.discriminator
            preview_history = rec.match_history or None
            preview_blocklisted = rec.handle in self._config.blocklist_handles
            if rec.community:
                preview_profile = rec.community.profile
        elif self._orchestrator and self._orchestrator.players:
            first = next(iter(self._orchestrator.players.values()))
            preview_handle = first.handle
            preview_profile_id = first.profile_id or first.discriminator
            preview_history = first.match_history or None
            if first.community:
                preview_profile = first.community.profile

        def on_saved(cfg: AppConfig) -> None:
            self._config = cfg
            if self._orchestrator:
                self._orchestrator.update_config(cfg)
            self._log("评分规则已保存")

        RuleEditorDialog(
            self,
            self._config,
            on_saved=on_saved,
            preview_handle=preview_handle,
            preview_profile_id=preview_profile_id,
            preview_profile=preview_profile,
            preview_history=preview_history,
            preview_blocklisted=preview_blocklisted,
        )

    def _open_settings(self) -> None:
        from antismurf.app.settings_dialog import SettingsDialog

        def on_saved(cfg: AppConfig) -> None:
            self._config = apply_memory_runtime_defaults(cfg)
            self._dry_run_var.set(self._config.dry_run)
            self._auto_kick_var.set(self._config.auto_kick_enabled)
            if self._orchestrator:
                self._orchestrator.update_config(self._config)
            self._profile = ProfileAssist(self._config)
            self._log("设置已保存")

        SettingsDialog(self, self._config, on_saved=on_saved)

    def _open_replay_credits(self) -> None:
        from antismurf.app.replay_credits_dialog import ReplayCreditsDialog

        def on_saved(cfg: AppConfig) -> None:
            self._config = apply_memory_runtime_defaults(cfg)
            if self._orchestrator:
                self._orchestrator.update_config(self._config)
            self._log("录像/积分设置已保存")

        ReplayCreditsDialog(
            self,
            self._config,
            orchestrator=self._orchestrator,
            loop=self._loop,
            on_saved=on_saved,
        )

    def _open_data_sources(self) -> None:
        self._open_replay_credits()

    def _blocklist(self, handle: str) -> None:
        if self._orchestrator and self._loop:
            asyncio.run_coroutine_threadsafe(
                self._orchestrator.blocklist_player(handle), self._loop
            )
            self._log(f"已加入黑名单并重新评估: {handle}")

    def _blacklist_mark(self, handle: str) -> None:
        if not self._orchestrator or not self._loop:
            return
        asyncio.run_coroutine_threadsafe(
            self._orchestrator.blacklist_and_mark(handle), self._loop
        )
        self._log(f"已一键拉黑 (+200 嫌疑分): {handle}")

    def _open_calibration(self) -> None:
        from antismurf.app.calibration import CalibrationWizard

        def on_saved(cfg: AppConfig) -> None:
            self._config = cfg
            if self._orchestrator:
                self._orchestrator.update_config(cfg)
            self._profile = ProfileAssist(cfg)
            self._log("校准配置已保存并应用")

        CalibrationWizard(
            self, self._config, on_saved=on_saved, orchestrator=self._orchestrator
        )

    def _downgrade(self, handle: str) -> None:
        if self._orchestrator and self._loop:
            asyncio.run_coroutine_threadsafe(
                self._orchestrator.downgrade_player(handle), self._loop
            )
            self._log(f"已降级嫌疑: {handle}")

    def _fetch_history(self, handle: str) -> None:
        from antismurf.app.history_dialog import HistoryDialog

        if not self._orchestrator:
            return

        def on_loaded(h: str, matches) -> None:
            self._orchestrator.set_player_history(h, matches)
            self._log(
                f"已加载 {h} 的 {len(matches)} 场战绩，并触发二次评估"
            )

        HistoryDialog(
            self,
            handle,
            self._config,
            get_profile_ref=self._orchestrator.get_profile_ref_sync,
            save_profile_ref=self._orchestrator.save_profile_ref_sync,
            get_match_history=self._orchestrator.get_match_history_sync,
            on_loaded=on_loaded,
        )

    def _kick(self, handle: str, slot_index: int | None = None) -> None:
        if not self._is_local_host:
            self._log("当前非房主，无法踢人")
            return
        if self._orchestrator and self._loop:
            ok = self._orchestrator.kick_player(handle)
            slot_part = (
                f" 槽位{ui_slot_label(slot_index)}"
                if slot_index is not None
                else ""
            )
            dry = self._config.dry_run
            hint = "（dry run 仅模拟，取消勾选以测试 OCR）" if dry else ""
            self._log(
                f"{'[dry_run] ' if dry else ''}踢出 {handle}{slot_part}: "
                f"{'成功' if ok else '失败'}{hint}"
            )

    def _whitelist(self, handle: str) -> None:
        if self._orchestrator and self._loop:
            asyncio.run_coroutine_threadsafe(
                self._orchestrator.whitelist_player(handle), self._loop
            )
            self._log(f"已加入白名单: {handle}")

    def _manual_refresh(self) -> None:
        """手动刷新:立即扫描一次房间玩家信息并确认更新。

        1.5 秒内再次点击(连续刷新)时,除强制重新确认句柄位置外,
        同时重新查看当前是否选择了 SC2 进程(进程失效自动重新选择)。
        """
        if not self._orchestrator or not self._loop:
            self._log("后台未就绪，无法刷新")
            return
        now = time.monotonic()
        rapid = (
            now - self._last_refresh_click_at
            < self._config.memory_handle_reconfirm_threshold_sec
        )
        self._last_refresh_click_at = now
        if rapid:
            self._refresh_sc2_windows()
            self._log("连续刷新：已重新确认 SC2 进程与句柄位置")
        future = asyncio.run_coroutine_threadsafe(
            self._orchestrator.refresh_lobby_now(force=rapid), self._loop
        )

        def done(f) -> None:
            try:
                ok = bool(f.result())
            except Exception as exc:
                ok = False
                logger.warning("Manual refresh failed: %s", exc)
            self.after(
                0,
                lambda: self._log(
                    "已手动刷新并确认房间玩家信息"
                    if ok
                    else "手动刷新失败：内存扫描未启用或未找到 SC2 进程"
                ),
            )

        future.add_done_callback(done)

    def _on_toggle_dry_run(self) -> None:
        self._config.dry_run = self._dry_run_var.get()
        if self._orchestrator:
            self._orchestrator.update_config(self._config)

    def _on_toggle_auto_kick(self) -> None:
        self._config.auto_kick_enabled = self._auto_kick_var.get()
        if self._orchestrator:
            self._orchestrator.update_config(self._config)

    def _open_whitelist_batch(self) -> None:
        """批量添加白名单(自动识别分隔符/补全前缀/校验)。"""
        if not self._orchestrator or not self._loop:
            self._log("后台未就绪，无法批量添加白名单")
            return
        from antismurf.app.whitelist_batch_dialog import WhitelistBatchDialog

        WhitelistBatchDialog(
            self,
            self._orchestrator,
            self._loop,
            on_log=self._log,
        )

    def _on_toggle_whitelist_mode(self) -> None:
        self._config.whitelist_mode = self._whitelist_mode_var.get()
        if self._orchestrator:
            self._orchestrator.update_config(self._config)
        self._log(
            "白名单模式已启用：仅保留白名单玩家，其余自动踢出"
            if self._config.whitelist_mode
            else "已切换回黑名单模式（按嫌疑分踢出）"
        )

    def on_close(self) -> None:
        if self._orchestrator and self._loop:
            asyncio.run_coroutine_threadsafe(
                self._orchestrator.stop(), self._loop
            )
        self.destroy()


def run_gui(config: AppConfig | None = None) -> None:
    app = AntiSmurfApp(config)
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
