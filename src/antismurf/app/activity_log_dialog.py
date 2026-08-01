from __future__ import annotations

from typing import TYPE_CHECKING

import customtkinter as ctk

if TYPE_CHECKING:
    from antismurf.app.orchestrator import Orchestrator


class ActivityLogDialog(ctk.CTkToplevel):
    def __init__(self, parent: ctk.CTk, orchestrator: Orchestrator) -> None:
        super().__init__(parent)
        self.title("活动日志")
        self.geometry("640x480")

        tabs = ctk.CTkTabview(self)
        tabs.pack(fill="both", expand=True, padx=10, pady=10)
        eval_tab = tabs.add("评估记录")
        kick_tab = tabs.add("踢人记录")

        eval_box = ctk.CTkTextbox(eval_tab)
        eval_box.pack(fill="both", expand=True, padx=6, pady=6)
        kick_box = ctk.CTkTextbox(kick_tab)
        kick_box.pack(fill="both", expand=True, padx=6, pady=6)

        for entry in orchestrator.fetch_evaluation_logs_sync():
            eval_box.insert(
                "end",
                f"[{entry.created_at:%m-%d %H:%M}] {entry.handle}  "
                f"{entry.tier} {entry.score:.0f}  {','.join(entry.rules)}\n",
            )
        for entry in orchestrator.fetch_kick_logs_sync():
            mode = "dry_run" if entry.dry_run else "live"
            status = "成功" if entry.success else "失败"
            kick_box.insert(
                "end",
                f"[{entry.created_at:%m-%d %H:%M}] {entry.handle}  "
                f"{status} ({mode})\n",
            )

        if not eval_box.get("1.0", "end").strip():
            eval_box.insert("end", "暂无评估记录\n")
        if not kick_box.get("1.0", "end").strip():
            kick_box.insert("end", "暂无踢人记录\n")

        eval_box.configure(state="disabled")
        kick_box.configure(state="disabled")
