from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from tkinter import filedialog, messagebox
from typing import Callable

import customtkinter as ctk

from antismurf.config.settings import AppConfig, ExpressionRule, save_user_config, _project_root
from antismurf.models.evaluation import MatchSummary
from antismurf.app.rule_picker_widgets import ExpressionBuilder
from antismurf.scoring.expression_engine import (
    OPERATORS,
    VARIABLE_CATALOG,
    RuleContext,
    evaluate_expression_rule,
)
from antismurf.scoring.presets import list_preset_names, load_preset_rules
from antismurf.scoring.rule_pack import (
    RulePackMeta,
    load_rule_pack,
    merge_rules,
    save_rule_pack,
    validate_rules,
)
from antismurf.config.expression_rules_io import expression_rule_from_dict


class RuleEditorDialog(ctk.CTkToplevel):
    def __init__(
        self,
        parent: ctk.CTk,
        config: AppConfig,
        on_saved: Callable[[AppConfig], None] | None = None,
        preview_handle: str | None = None,
        preview_profile_id: int | None = None,
        preview_profile=None,
        preview_history: list[MatchSummary] | None = None,
        preview_blocklisted: bool = False,
    ) -> None:
        super().__init__(parent)
        self.title("评分规则编辑器")
        self.geometry("960x720")
        self._config = config
        self._on_saved = on_saved
        self._rules: list[ExpressionRule] = list(config.expression_rules)
        self._selected_idx: int | None = None
        self._preview_ctx = RuleContext(
            handle=preview_handle or "",
            profile_id=preview_profile_id,
            profile=preview_profile,
            blocklisted=preview_blocklisted,
            match_history=preview_history,
        )

        top = ctk.CTkFrame(self)
        top.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(top, text="预设:").pack(side="left", padx=4)
        self._preset_var = ctk.StringVar(value=config.scoring_preset)
        self._preset_menu = ctk.CTkOptionMenu(
            top,
            variable=self._preset_var,
            values=list_preset_names(),
            command=self._on_preset_selected,
        )
        self._preset_menu.pack(side="left", padx=4)
        ctk.CTkButton(top, text="导入规则", width=80, command=self._import_rules).pack(
            side="right", padx=4
        )
        ctk.CTkButton(top, text="导出规则", width=80, command=self._export_rules).pack(
            side="right", padx=4
        )
        ctk.CTkButton(top, text="添加规则", width=80, command=self._add_rule).pack(
            side="right", padx=4
        )
        ctk.CTkButton(top, text="删除规则", width=80, command=self._delete_rule).pack(
            side="right", padx=4
        )
        ctk.CTkButton(
            top, text="保存", width=80, fg_color="#2d6a4f", command=self._save
        ).pack(side="right", padx=4)
        ctk.CTkButton(top, text="使用说明", width=80, command=self._open_help).pack(
            side="left", padx=4
        )
        ctk.CTkButton(
            top, text="AI 助手", width=80, command=self._open_ai_assistant
        ).pack(side="left", padx=4)
        ctk.CTkButton(top, text="IDE 编辑", width=80, command=self._open_ide_editor).pack(
            side="left", padx=4
        )
        ctk.CTkButton(
            top, text="从文件重载", width=90, command=self._reload_from_file
        ).pack(side="left", padx=4)

        body = ctk.CTkFrame(self)
        body.pack(fill="both", expand=True, padx=10, pady=5)

        left = ctk.CTkFrame(body, width=260)
        left.pack(side="left", fill="y", padx=(0, 8))
        left.pack_propagate(False)
        ctk.CTkLabel(left, text="规则列表", anchor="w").pack(fill="x", padx=6, pady=4)
        self._rule_list = ctk.CTkScrollableFrame(left)
        self._rule_list.pack(fill="both", expand=True, padx=4, pady=4)

        right = ctk.CTkScrollableFrame(body, label_text="规则编辑")
        right.pack(side="left", fill="both", expand=True)
        self._editor = right
        self._fields: dict[str, ctk.CTkBaseClass] = {}
        self._build_editor_form()
        self._refresh_rule_list()
        if self._rules:
            self._select_rule(0)

        preview_frame = ctk.CTkFrame(self)
        preview_frame.pack(fill="x", padx=10, pady=8)
        ctk.CTkLabel(preview_frame, text="预览:", anchor="w").pack(
            side="left", padx=6
        )
        self._preview_label = ctk.CTkLabel(
            preview_frame,
            text=self._build_preview_text(),
            anchor="w",
            justify="left",
            wraplength=860,
        )
        self._preview_label.pack(fill="x", padx=6, pady=4)

    def _build_editor_form(self) -> None:
        parent = self._editor

        def row(label: str, key: str, widget_factory) -> None:
            fr = ctk.CTkFrame(parent, fg_color="transparent")
            fr.pack(fill="x", pady=3)
            ctk.CTkLabel(fr, text=label, width=100, anchor="w").pack(side="left")
            w = widget_factory(fr)
            w.pack(side="left", fill="x", expand=True, padx=4)
            self._fields[key] = w

        row("启用", "enabled", lambda p: ctk.CTkCheckBox(p, text=""))
        row("ID", "id", lambda p: ctk.CTkEntry(p))
        row("名称", "label", lambda p: ctk.CTkEntry(p))

        ctk.CTkLabel(
            parent,
            text="运算式：从菜单选变量，可选 A−B 再与阈值比较；条件为真(1)时加权重分",
            anchor="w",
        ).pack(fill="x", pady=(8, 2))
        self._expr = ExpressionBuilder(parent, on_change=self._update_preview)
        self._expr.pack(fill="x", pady=4)

        row("权重(真)", "weight", lambda p: ctk.CTkEntry(p))
        row("权重(假)", "else_weight", lambda p: ctk.CTkEntry(p))
        row("最少对局", "min_games", lambda p: ctk.CTkEntry(p))
        ctk.CTkButton(
            parent, text="应用当前规则", command=self._apply_editor
        ).pack(pady=8)

    def _refresh_rule_list(self) -> None:
        for child in self._rule_list.winfo_children():
            child.destroy()
        for idx, rule in enumerate(self._rules):
            text = f"{'[x]' if rule.enabled else '[ ]'} {rule.label or rule.id}"
            btn = ctk.CTkButton(
                self._rule_list,
                text=text,
                anchor="w",
                fg_color="#333" if idx != self._selected_idx else "#1f538d",
                command=lambda i=idx: self._select_rule(i),
            )
            btn.pack(fill="x", pady=2)

    def _select_rule(self, idx: int) -> None:
        self._apply_editor(silent=True)
        self._selected_idx = idx
        rule = self._rules[idx]
        cast = self._fields
        cast["enabled"].select() if rule.enabled else cast["enabled"].deselect()
        for key in ("id", "label", "weight", "else_weight", "min_games"):
            entry = cast[key]
            entry.delete(0, "end")
            entry.insert(0, str(getattr(rule, key, "")))
        self._expr.set_expression(
            rule.left,
            rule.op if rule.op in OPERATORS else ">=",
            rule.right,
            getattr(rule, "right2", ""),
            arith_op=getattr(rule, "arith_op", "") or "",
            middle=getattr(rule, "middle", "") or "",
        )
        self._refresh_rule_list()
        self._update_preview()

    def _apply_editor(self, silent: bool = False) -> None:
        if self._selected_idx is None:
            return
        rule = self._rules[self._selected_idx]
        f = self._fields
        rule.enabled = bool(f["enabled"].get())
        rule.id = f["id"].get().strip() or rule.id
        rule.label = f["label"].get().strip()
        rule.left = self._expr.get_left()
        rule.arith_op = self._expr.get_arith_op()
        rule.middle = self._expr.get_middle()
        rule.op = self._expr.get_op()
        rule.right = self._parse_field_value(self._expr.get_right())
        rule.right2 = self._parse_field_value(self._expr.get_right2())
        try:
            rule.weight = float(f["weight"].get() or 0)
        except ValueError:
            pass
        try:
            rule.else_weight = float(f["else_weight"].get() or 0)
        except ValueError:
            pass
        try:
            rule.min_games = int(f["min_games"].get() or 0)
        except ValueError:
            pass
        if not silent:
            self._refresh_rule_list()
            self._update_preview()

    def _parse_field_value(self, text: str) -> str | float | bool:
        text = text.strip()
        if text.lower() == "true":
            return True
        if text.lower() == "false":
            return False
        if text in VARIABLE_CATALOG:
            return text
        try:
            return float(text)
        except ValueError:
            return text

    def _add_rule(self) -> None:
        rid = f"custom_{uuid.uuid4().hex[:6]}"
        self._rules.append(
            ExpressionRule(
                id=rid,
                label="新规则",
                left="mmr_playlike.max",
                arith_op="-",
                middle="mmr.min",
                op=">",
                right=800,
                weight=10,
            )
        )
        self._select_rule(len(self._rules) - 1)

    def _delete_rule(self) -> None:
        if self._selected_idx is None:
            return
        del self._rules[self._selected_idx]
        self._selected_idx = None
        self._refresh_rule_list()
        if self._rules:
            self._select_rule(0)
        self._update_preview()

    def _open_ai_assistant(self) -> None:
        """打开 AI 规则助手:填 API Key 用自然语言生成规则。"""
        from antismurf.app.ai_rule_dialog import AiRuleDialog

        def on_rules(rules: list[ExpressionRule]) -> None:
            self._rules.extend(rules)
            self._selected_idx = None
            self._refresh_rule_list()
            if self._rules:
                self._select_rule(len(self._rules) - 1)
            self._update_preview()

        def on_config_saved(cfg: AppConfig) -> None:
            self._config = cfg
            if self._on_saved:
                self._on_saved(cfg)

        AiRuleDialog(
            self,
            self._config,
            on_rules=on_rules,
            on_config_saved=on_config_saved,
        )

    def _open_ide_editor(self) -> None:
        """导出当前规则到临时规则文件并用本地 IDE(VSCode)打开。"""
        self._apply_editor(silent=True)
        path = _project_root() / "config" / "rule_edit.toml"
        try:
            save_rule_pack(path, self._rules, meta=RulePackMeta(name="rule_edit"))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("导出失败", str(exc), parent=self)
            return
        code = shutil.which("code")
        if code:
            subprocess.Popen([code, str(path)])
        else:
            os.startfile(str(path))  # type: ignore[attr-defined]
        messagebox.showinfo(
            "已打开编辑器",
            "请在编辑器中修改规则后,点击「从文件重载」应用",
            parent=self,
        )

    def _reload_from_file(self) -> None:
        """从 config/rule_edit.toml 加载编辑后的规则。"""
        path = _project_root() / "config" / "rule_edit.toml"
        if not path.exists():
            messagebox.showerror(
                "未找到规则文件", "请先使用「IDE 编辑」导出规则文件", parent=self
            )
            return
        try:
            _meta, imported = load_rule_pack(path)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("加载失败", str(exc), parent=self)
            return
        validation = validate_rules(imported)
        if validation.errors:
            messagebox.showerror(
                "规则校验失败", "\n".join(validation.errors[:8]), parent=self
            )
            return
        self._rules = imported
        self._selected_idx = None
        self._refresh_rule_list()
        if self._rules:
            self._select_rule(0)
        self._update_preview()
        messagebox.showinfo("重载成功", f"已加载 {len(imported)} 条规则", parent=self)

    def _on_preset_selected(self, name: str) -> None:
        raw = load_preset_rules(name)
        self._rules = [expression_rule_from_dict(r) for r in raw]
        self._config.scoring_preset = name
        self._selected_idx = None
        self._refresh_rule_list()
        if self._rules:
            self._select_rule(0)

    def _import_rules(self) -> None:
        path = filedialog.askopenfilename(
            title="导入规则包",
            filetypes=[
                ("规则包", "*.toml *.txt"),
                ("TOML", "*.toml"),
                ("文本", "*.txt"),
                ("所有文件", "*.*"),
            ],
        )
        if not path:
            return
        try:
            meta, imported = load_rule_pack(path)
        except Exception as exc:
            messagebox.showerror("导入失败", str(exc), parent=self)
            return

        validation = validate_rules(imported)
        lines = [
            f"规则包: {meta.name or path}",
            f"规则数量: {len(imported)}",
        ]
        if validation.warnings:
            lines.append("警告:")
            lines.extend(f"  - {w}" for w in validation.warnings[:8])
        if validation.errors:
            lines.append("错误:")
            lines.extend(f"  - {e}" for e in validation.errors[:8])
            messagebox.showerror("导入失败", "\n".join(lines), parent=self)
            return

        merge = messagebox.askyesno(
            "导入方式",
            "\n".join(lines)
            + "\n\n选择「是」= 按 id 合并覆盖；选择「否」= 完全替换当前规则",
            parent=self,
        )
        mode = "merge_by_id" if merge else "replace"
        self._rules = merge_rules(self._rules, imported, mode)
        self._selected_idx = None
        self._refresh_rule_list()
        if self._rules:
            self._select_rule(0)
        self._update_preview()
        messagebox.showinfo("导入成功", f"已导入 {len(imported)} 条规则", parent=self)

    def _export_rules(self) -> None:
        self._apply_editor(silent=True)
        path = filedialog.asksaveasfilename(
            title="导出规则包",
            defaultextension=".txt",
            filetypes=[
                ("文本规则包", "*.txt"),
                ("TOML", "*.toml"),
                ("所有文件", "*.*"),
            ],
        )
        if not path:
            return
        meta = RulePackMeta(name=self._preset_var.get() or "自定义规则")
        try:
            save_rule_pack(path, self._rules, meta)
        except Exception as exc:
            messagebox.showerror("导出失败", str(exc), parent=self)
            return
        messagebox.showinfo("导出成功", f"已保存到:\n{path}", parent=self)

    def _build_preview_text(self) -> str:
        if not self._preview_ctx.handle:
            return "未选择预览玩家（从玩家行打开规则编辑器可预览）"
        lines = [f"玩家: {self._preview_ctx.handle}"]
        for rule in self._rules:
            if not rule.enabled:
                continue
            hit = evaluate_expression_rule(rule, self._preview_ctx)
            if hit:
                lines.append(f"  触发: {hit.reason} (+{hit.score_delta})")
            else:
                lines.append(f"  未触发: {rule.label or rule.id}")
        return "\n".join(lines)

    def _update_preview(self) -> None:
        self._preview_label.configure(text=self._build_preview_text())

    def _save(self) -> None:
        self._apply_editor(silent=True)
        self._config.expression_rules = list(self._rules)
        self._config.scoring_preset = self._preset_var.get()
        save_user_config(self._config)
        if self._on_saved:
            self._on_saved(self._config)

    def _open_help(self) -> None:
        manual = _project_root() / "docs" / "规则设置手册.md"
        if not manual.is_file():
            messagebox.showerror("使用说明", f"未找到手册文件:\n{manual}")
            return
        text = manual.read_text(encoding="utf-8")
        win = ctk.CTkToplevel(self)
        win.title("规则设置与 UI 校准 — 使用说明")
        win.geometry("820x640")
        win.transient(self)
        box = ctk.CTkTextbox(win, wrap="word", font=ctk.CTkFont(size=13))
        box.pack(fill="both", expand=True, padx=12, pady=12)
        box.insert("1.0", text)
        box.configure(state="disabled")
        ctk.CTkButton(win, text="关闭", width=80, command=win.destroy).pack(pady=(0, 10))
