from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from antismurf.config.settings import AppConfig
from antismurf.models.evaluation import MatchSummary
from antismurf.review.profile_parser import parse_profile_ids_text


class HistoryDialog(ctk.CTkToplevel):
    def __init__(
        self,
        parent: ctk.CTk,
        handle: str,
        config: AppConfig,
        get_profile_ref: Callable[[str], tuple[int, int, int] | None],
        save_profile_ref: Callable[[str, int, int, int], None],
        get_match_history: Callable[[str], list[MatchSummary]],
        on_loaded: Callable[[str, list[MatchSummary]], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.title(f"本地录像战绩 — {handle}")
        self.geometry("560x480")
        self._handle = handle
        self._config = config
        self._get_match_history = get_match_history
        self._get_profile_ref = get_profile_ref
        self._save_profile_ref = save_profile_ref
        self._on_loaded = on_loaded

        ctk.CTkLabel(
            self,
            text="从本地 KS2 录像索引加载该句柄的战绩（需先在「数据源」确认并扫描录像）",
        ).pack(padx=12, pady=(12, 4), anchor="w")

        ctk.CTkLabel(
            self,
            text="可选：粘贴 SC2 档案链接或 region/realm/profile_id 并保存",
        ).pack(padx=12, pady=(0, 4), anchor="w")

        self._id_entry = ctk.CTkEntry(self, width=480)
        self._id_entry.pack(padx=12, pady=4)
        ref = get_profile_ref(handle)
        if ref:
            self._id_entry.insert(0, f"{ref[0]}/{ref[1]}/{ref[2]}")
        else:
            self._try_prefill_from_clipboard()

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(padx=12, pady=8, anchor="w")
        ctk.CTkButton(
            btn_row, text="加载录像战绩", command=self._fetch
        ).pack(side="left", padx=4)
        ctk.CTkButton(btn_row, text="保存档案 ID", command=self._save_id).pack(
            side="left", padx=4
        )

        self._status = ctk.CTkLabel(self, text="")
        self._status.pack(padx=12, anchor="w")

        self._text = ctk.CTkTextbox(self, height=300)
        self._text.pack(fill="both", expand=True, padx=12, pady=8)

        if not self._config.replays_enabled:
            self._status.configure(text="提示: 请在配置中启用 [replays] 并完成数据源确认")

    def _try_prefill_from_clipboard(self) -> None:
        from antismurf.utils.clipboard import read_clipboard

        text = read_clipboard()
        if not text:
            return
        ref = parse_profile_ids_text(text)
        if ref:
            self._id_entry.insert(0, f"{ref.region_id}/{ref.realm_id}/{ref.profile_id}")
            self._status.configure(text="已从剪贴板读取档案 ID")

    def _save_id(self) -> None:
        ref = parse_profile_ids_text(self._id_entry.get())
        if not ref:
            self._status.configure(text="无法解析档案 ID")
            return
        self._save_profile_ref(
            self._handle, ref.region_id, ref.realm_id, ref.profile_id
        )
        self._status.configure(text="档案 ID 已保存")

    def _fetch(self) -> None:
        if not self._config.replays_enabled:
            self._status.configure(text="本地录像索引未启用")
            return
        self._status.configure(text="加载中...")
        self._text.delete("1.0", "end")
        matches = self._get_match_history(self._handle)
        self._show_matches(matches)

    def _show_matches(self, matches: list[MatchSummary]) -> None:
        if not matches:
            self._status.configure(
                text="无本地录像战绩（请确认数据源并扫描 KS2 录像）"
            )
            return
        self._status.configure(text=f"共 {len(matches)} 场（来自本地录像）")
        lines = []
        for m in matches:
            ts = m.played_at.strftime("%Y-%m-%d %H:%M") if m.played_at else "?"
            lines.append(
                f"[{ts}] {m.game_type:8} {m.decision:8} {m.map_name}"
            )
        self._text.insert("end", "\n".join(lines))
        if self._on_loaded:
            self._on_loaded(self._handle, matches)
