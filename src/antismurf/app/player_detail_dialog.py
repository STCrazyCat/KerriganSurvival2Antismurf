from __future__ import annotations

import customtkinter as ctk

from antismurf.models.evaluation import PlayerRecord

TIER_LABELS = {
    "low": "低",
    "medium": "中",
    "high": "高",
    "critical": "极高",
}


class PlayerDetailDialog(ctk.CTkToplevel):
    def __init__(self, parent: ctk.CTk, record: PlayerRecord) -> None:
        super().__init__(parent)
        self.title(f"玩家详情 — {record.handle}")
        self.geometry("640x560")

        text = ctk.CTkTextbox(self)
        text.pack(fill="both", expand=True, padx=12, pady=12)

        lines = [
            f"玩家 ID: {record.display_name or '-'}",
            f"句柄: {record.handle}",
            f"备注: {record.remark or '-'}",
            f"档案路径: {record.profile_ref or '-'}",
            f"嫌疑等级: {TIER_LABELS.get(record.tier, record.tier)}",
            f"分数: {record.score:.1f}",
            f"槽位: {record.slot_index + 1}",
            f"白名单: {'是' if record.whitelisted else '否'}",
            "",
        ]

        profile = record.community.profile if record.community else None
        if profile:
            d = profile.derived
            lines += [
                "核心 MMR:",
                f"  凯瑞甘: {profile.core_mmr.kerrigan or '-'}",
                f"  生存者: {profile.core_mmr.survivor or '-'}",
                "",
                "反推核心 playlike:",
                f"  凯瑞甘: {d.core_playlike.kerrigan or '-'}",
                f"  生存者: {d.core_playlike.survivor or '-'}",
                "",
                "playlike 高于核心 (lift):",
                f"  凯瑞甘: {d.lift_core_kerrigan or '-'}",
                f"  生存者: {d.lift_core_survivor or '-'}",
                f"  最大: {d.lift_core_max or '-'}",
                "",
                "异常对局 (playlike >> core):",
                f"  计数: {d.playlike_spike_count} "
                f"(生存者 {d.playlike_spike_count_survivor} / "
                f"凯瑞甘 {d.playlike_spike_count_kerrigan})",
                f"  最大超出: {d.playlike_spike_max or '-'}",
                f"  平均超出: {d.playlike_spike_avg or '-'}",
                "",
                f"playlike 对局数: {d.data_quality.playlike_game_count}",
                f"全局 playlike 均值: {d.playlike_avg_all or '-'}",
                "",
            ]
            if d.playlike_avg_by_archetype:
                lines.append("按职业 archetype playlike 均值:")
                for k, v in sorted(d.playlike_avg_by_archetype.items()):
                    lines.append(f"  {k}: {v:.0f}")
                lines.append("")
            if profile.roles:
                lines.append("角色 class MMR (前 8):")
                top = sorted(
                    profile.roles.values(),
                    key=lambda r: r.mmr or 0,
                    reverse=True,
                )[:8]
                for r in top:
                    lines.append(
                        f"  {r.role_name} [{r.archetype or '?'}]: "
                        f"mmr={r.mmr or '-'} class={r.class_mmr or '-'}"
                    )
                lines.append("")
        elif record.community:
            c = record.community
            lines += [
                "社区数据:",
                f"  MMR: {c.mmr if c.mmr is not None else '-'}",
                f"  MMR_playlike: {c.mmr_playlike if c.mmr_playlike is not None else '-'}",
                "",
            ]

        if record.rule_reasons:
            lines.append("命中规则:")
            for reason in record.rule_reasons:
                lines.append(f"  · {reason}")
        elif record.triggered_rules:
            lines.append("命中规则 ID:")
            for rule in record.triggered_rules:
                lines.append(f"  · {rule}")

        if record.match_history:
            lines += ["", f"已加载战绩: {len(record.match_history)} 场"]
            for m in record.match_history[:10]:
                ts = m.played_at.strftime("%Y-%m-%d") if m.played_at else "?"
                lines.append(f"  [{ts}] {m.decision} {m.game_type} {m.map_name}")

        text.insert("end", "\n".join(lines))
        text.configure(state="disabled")

        ctk.CTkButton(
            self,
            text="编辑评分规则",
            command=lambda: self._open_rules(record),
        ).pack(pady=8)

    def _open_rules(self, record: PlayerRecord) -> None:
        app = self.winfo_toplevel()
        if hasattr(app, "_open_rule_editor"):
            app._open_rule_editor(record.handle)
