from __future__ import annotations

import time
from typing import Callable

import customtkinter as ctk

from antismurf.config.settings import AppConfig, save_user_config


class SettingsDialog(ctk.CTkToplevel):
    def __init__(
        self,
        parent: ctk.CTk,
        config: AppConfig,
        on_saved: Callable[[AppConfig], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.title("设置")
        self.geometry("480x480")
        self._config = config
        self._on_saved = on_saved

        scroll = ctk.CTkScrollableFrame(self, label_text="评分与行为")
        scroll.pack(fill="both", expand=True, padx=10, pady=10)

        self._entries: dict[str, ctk.CTkEntry] = {}

        def add_row(label: str, key: str, value: str, show: str = "") -> None:
            row = ctk.CTkFrame(scroll, fg_color="transparent")
            row.pack(fill="x", pady=4)
            ctk.CTkLabel(row, text=label, width=140, anchor="w").pack(
                side="left"
            )
            entry = ctk.CTkEntry(row, width=260, show=show)
            entry.insert(0, value)
            entry.pack(side="left", padx=6)
            self._entries[key] = entry

        add_row("踢人阈值", "kick_threshold", str(config.kick_threshold))
        add_row("中嫌疑线", "tier_medium", str(config.tier_medium))
        add_row("高嫌疑线", "tier_high", str(config.tier_high))
        add_row("极高嫌疑线", "tier_critical", str(config.tier_critical))
        add_row("踢人菜单下按次数", "kick_menu_down_presses", str(config.kick_menu_down_presses))
        add_row("档案菜单下按次数", "profile_menu_down_presses", str(config.profile_menu_down_presses))

        ctk.CTkLabel(scroll, text="分数颜色（主界面/历史界面）", anchor="w").pack(
            fill="x", pady=(12, 4)
        )
        add_row("正分（+）", "score_color_positive", config.score_color_positive)
        add_row("负分（−）", "score_color_negative", config.score_color_negative)
        add_row("零分（0）", "score_color_zero", config.score_color_zero)

        ctk.CTkLabel(scroll, text="社区服务器", anchor="w").pack(
            fill="x", pady=(12, 4)
        )
        add_row(
            "Provider (disabled/stub/http/ks2wiki)",
            "community_provider",
            config.community_provider,
        )
        add_row("Base URL", "community_base_url", config.community_base_url)
        add_row("API Key", "community_api_key", config.community_api_key, show="*")

        self._notify_var = ctk.BooleanVar(value=config.notify_high_suspicion)
        ctk.CTkCheckBox(
            scroll,
            text="高嫌疑 Windows 通知",
            variable=self._notify_var,
        ).pack(anchor="w", padx=4, pady=8)

        ctk.CTkButton(
            self, text="保存", fg_color="#2d6a4f", command=self._save
        ).pack(padx=12, pady=12, anchor="e")

    def _save(self) -> None:
        cfg = self._config
        cfg.kick_threshold = float(self._entries["kick_threshold"].get())
        cfg.tier_medium = float(self._entries["tier_medium"].get())
        cfg.tier_high = float(self._entries["tier_high"].get())
        cfg.tier_critical = float(self._entries["tier_critical"].get())
        cfg.kick_menu_down_presses = int(self._entries["kick_menu_down_presses"].get())
        cfg.profile_menu_down_presses = int(
            self._entries["profile_menu_down_presses"].get()
        )
        cfg.score_color_positive = self._entries["score_color_positive"].get().strip() or "#ff5c5c"
        cfg.score_color_negative = self._entries["score_color_negative"].get().strip() or "#57d957"
        cfg.score_color_zero = self._entries["score_color_zero"].get().strip() or "#ffffff"
        cfg.community_provider = self._entries["community_provider"].get().strip()
        cfg.community_base_url = self._entries["community_base_url"].get().strip()
        cfg.community_api_key = self._entries["community_api_key"].get().strip()
        cfg.notify_high_suspicion = self._notify_var.get()
        save_user_config(cfg)
        if self._on_saved:
            self._on_saved(cfg)
