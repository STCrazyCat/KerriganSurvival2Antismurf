"""Recent detected players with MMR comparison and quick mark/trust actions."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Callable

import customtkinter as ctk

from antismurf.app.score_theme import score_color
from antismurf.data.sighting_compare import SightingComparison
from antismurf.storage.sightings import PlayerSightingEntry

if TYPE_CHECKING:
    from antismurf.app.orchestrator import Orchestrator

TIER_COLORS = {
    "low": "#2d6a4f",
    "medium": "#b08900",
    "high": "#d00000",
    "critical": "#9d0208",
}


class PlayerHistoryDialog(ctk.CTkToplevel):
    def __init__(
        self,
        parent: ctk.CTk,
        *,
        orchestrator: Orchestrator,
        loop: asyncio.AbstractEventLoop | None = None,
        on_log: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.title("识别历史")
        self.geometry("1280x680")
        self._orchestrator = orchestrator
        self._loop = loop
        self._on_log = on_log
        self._rows: list[ctk.CTkFrame] = []
        self._compare_labels: dict[str, ctk.CTkLabel] = {}
        self._compare_task: asyncio.Future | None = None

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=10, pady=(10, 4))
        self._summary = ctk.CTkLabel(
            top,
            text="近期在大厅识别到的玩家（按最近出现排序）",
            anchor="w",
        )
        self._summary.pack(side="left", padx=4)
        ctk.CTkButton(
            top, text="对比刷新", width=88, command=self._refresh_comparisons
        ).pack(side="right", padx=4)
        ctk.CTkButton(top, text="刷新", width=70, command=self._reload).pack(
            side="right", padx=4
        )

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(0, 4))
        for text, width in [
            ("句柄", 140),
            ("战队", 64),
            ("昵称", 80),
            ("记录MMR", 120),
            ("记录PL", 100),
            ("MMR/PL 变化", 380),
            ("嫌疑", 36),
            ("分数", 36),
            ("最近", 76),
            ("次数", 36),
            ("操作", 180),
        ]:
            ctk.CTkLabel(header, text=text, width=width, anchor="w").pack(
                side="left", padx=2
            )

        self._list = ctk.CTkScrollableFrame(self, label_text="玩家列表")
        self._list.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self._reload()

    def _reload(self) -> None:
        for row in self._rows:
            row.destroy()
        self._rows.clear()
        self._compare_labels.clear()

        entries = self._orchestrator.fetch_player_sightings_sync()
        marked = self._orchestrator.marked_handles()
        trusted = self._orchestrator.trusted_handles()
        self._summary.configure(
            text=(
                f"共 {len(entries)} 名玩家"
                f"（已标记 {len(marked)}，信任 -20 {len(trusted)}）"
            )
        )

        if not entries:
            empty = ctk.CTkLabel(
                self._list,
                text="暂无识别记录。进入 KS2 房间后会自动记录扫描到的玩家。",
                anchor="w",
                wraplength=900,
            )
            empty.pack(fill="x", pady=12, padx=4)
            self._rows.append(empty)
            return

        for entry in entries:
            self._rows.append(
                self._create_row(
                    entry,
                    marked=entry.handle in marked,
                    trusted=entry.handle in trusted,
                )
            )

        self._refresh_comparisons()

    def _create_row(
        self,
        entry: PlayerSightingEntry,
        *,
        marked: bool,
        trusted: bool,
    ) -> ctk.CTkFrame:
        row = ctk.CTkFrame(self._list)
        row.pack(fill="x", pady=2)

        recorded_mmr = (
            f"{entry.mmr:.0f}" if entry.mmr is not None else "-"
        )
        recorded_pl = (
            f"{entry.mmr_playlike:.0f}"
            if entry.mmr_playlike is not None
            else "-"
        )
        last_seen = entry.last_seen_at.strftime("%m-%d %H:%M")

        for text, width in [
            (entry.handle, 140),
            (entry.team_name or "-", 64),
            (entry.nickname, 80),
            (recorded_mmr, 120),
            (recorded_pl, 100),
        ]:
            ctk.CTkLabel(row, text=text, width=width, anchor="w").pack(
                side="left", padx=2
            )

        compare_lbl = ctk.CTkLabel(
            row,
            text="对比加载中…",
            width=380,
            anchor="w",
            text_color="#888888",
        )
        compare_lbl.pack(side="left", padx=2)
        self._compare_labels[entry.handle] = compare_lbl

        tier_lbl = ctk.CTkLabel(
            row,
            text=entry.tier_label,
            width=36,
            anchor="w",
            text_color=TIER_COLORS.get(entry.tier, "white"),
        )
        tier_lbl.pack(side="left", padx=2)

        score_lbl = ctk.CTkLabel(
            row,
            text=f"{entry.score:.0f}",
            width=36,
            anchor="w",
            text_color=score_color(entry.score, self._orchestrator.config),
        )
        score_lbl.pack(side="left", padx=2)
        for text, width in [
            (last_seen, 76),
            (str(entry.seen_count), 36),
        ]:
            ctk.CTkLabel(row, text=text, width=width, anchor="w").pack(
                side="left", padx=2
            )

        btn_frame = ctk.CTkFrame(row, fg_color="transparent")
        btn_frame.pack(side="left", padx=2)
        mark_btn = ctk.CTkButton(
            btn_frame,
            text="已拉黑" if marked else "拉黑+200",
            width=72,
            fg_color="#555" if marked else "#8a6d00",
            state="disabled" if marked else "normal",
            command=lambda h=entry.handle: self._mark_handle(h),
        )
        mark_btn.pack(side="left", padx=2)
        trust_btn = ctk.CTkButton(
            btn_frame,
            text="已信任" if trusted else "白名单-20",
            width=72,
            fg_color="#555" if trusted else "#2d6a4f",
            state="disabled" if trusted else "normal",
            command=lambda h=entry.handle: self._trust_handle(h),
        )
        trust_btn.pack(side="left", padx=2)
        row._mark_btn = mark_btn  # type: ignore[attr-defined]
        row._trust_btn = trust_btn  # type: ignore[attr-defined]
        return row

    def _refresh_comparisons(self) -> None:
        if self._loop is None:
            for lbl in self._compare_labels.values():
                lbl.configure(text="无后台连接，无法对比", text_color="#888888")
            return

        for lbl in self._compare_labels.values():
            lbl.configure(text="对比加载中…", text_color="#888888")

        future = asyncio.run_coroutine_threadsafe(
            self._orchestrator.fetch_sighting_comparisons(),
            self._loop,
        )
        self._compare_task = future

        def _done(fut: asyncio.Future) -> None:
            try:
                comparisons: list[SightingComparison] = fut.result()
            except Exception as exc:
                self.after(
                    0,
                    lambda: self._apply_compare_error(str(exc)),
                )
                return
            self.after(0, lambda: self._apply_comparisons(comparisons))

        future.add_done_callback(_done)

    def _apply_compare_error(self, message: str) -> None:
        text = f"对比失败: {message[:80]}"
        for lbl in self._compare_labels.values():
            lbl.configure(text=text, text_color="#d00000")

    def _apply_comparisons(self, comparisons: list[SightingComparison]) -> None:
        by_handle = {item.entry.handle: item for item in comparisons}
        for handle, lbl in self._compare_labels.items():
            item = by_handle.get(handle)
            if item is None:
                lbl.configure(text="无对比数据", text_color="#888888")
                continue
            if item.fetch_error:
                lbl.configure(
                    text=item.summary,
                    text_color="#d00000",
                )
                continue
            lbl.configure(
                text=item.summary,
                text_color="#cccccc" if item.metric_deltas else "#888888",
            )

    def _mark_handle(self, handle: str) -> None:
        if self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(
            self._orchestrator.blacklist_and_mark(handle),
            self._loop,
        )
        if self._on_log:
            self._on_log(f"已一键拉黑 {handle} (+200 嫌疑分)")
        self.after(400, self._reload)

    def _trust_handle(self, handle: str) -> None:
        if self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(
            self._orchestrator.trust_player_handle(
                handle,
                label="历史页信任白名单",
            ),
            self._loop,
        )
        if self._on_log:
            self._on_log(f"已将 {handle} 加入信任白名单 (-20)")
        self.after(400, self._reload)
