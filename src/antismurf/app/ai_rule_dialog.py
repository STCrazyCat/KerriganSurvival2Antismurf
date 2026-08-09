"""AI rule authoring dialog: natural language -> ExpressionRule list."""

from __future__ import annotations

import asyncio
import threading
from typing import Callable

import customtkinter as ctk

from antismurf.config.settings import AppConfig, ExpressionRule, save_user_config
from antismurf.scoring.ai_rule_advisor import (
    build_rules_prompt,
    parse_ai_rules_response,
    request_rules,
)


class AiRuleDialog(ctk.CTkToplevel):
    def __init__(
        self,
        parent: ctk.CTk,
        config: AppConfig,
        on_rules: Callable[[list[ExpressionRule]], None],
        on_config_saved: Callable[[AppConfig], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.title("AI 规则助手")
        self.geometry("720x660")
        self._config = config
        self._on_rules = on_rules
        self._on_config_saved = on_config_saved
        self._generated: list[ExpressionRule] = []

        cfg_frame = ctk.CTkFrame(self)
        cfg_frame.pack(fill="x", padx=10, pady=(10, 4))
        self._entries: dict[str, ctk.CTkEntry] = {}

        def cfg_row(label: str, key: str) -> None:
            fr = ctk.CTkFrame(cfg_frame, fg_color="transparent")
            fr.pack(fill="x", pady=2)
            ctk.CTkLabel(fr, text=label, width=100, anchor="w").pack(side="left")
            entry = ctk.CTkEntry(fr, show="*" if "key" in key else "")
            entry.insert(0, str(getattr(self._config, key, "")))
            entry.pack(side="left", fill="x", expand=True, padx=4)
            self._entries[key] = entry

        cfg_row("API 地址", "ai_api_base_url")
        cfg_row("API Key", "ai_api_key")
        cfg_row("模型", "ai_model")
        ctk.CTkLabel(
            cfg_frame,
            text="支持 OpenAI 兼容接口(DeepSeek / Kimi / OpenAI / OpenRouter 等)",
            text_color="#888888",
            anchor="w",
        ).pack(fill="x", padx=2, pady=(2, 0))

        ctk.CTkLabel(
            self,
            text="用自然语言描述规则需求,例如:「凯瑞甘核心 MMR 高于 3000 且 playlike 对局数 ≥ 5 时,加 30 嫌疑分」",
            anchor="w",
            wraplength=680,
        ).pack(fill="x", padx=10, pady=4)
        self._requirement = ctk.CTkTextbox(self, height=120)
        self._requirement.pack(fill="x", padx=10, pady=4)

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=10, pady=4)
        self._gen_btn = ctk.CTkButton(btn_row, text="生成规则", command=self._generate)
        self._gen_btn.pack(side="left")
        ctk.CTkButton(
            btn_row,
            text="追加到规则列表",
            fg_color="#2d6a4f",
            command=self._apply,
        ).pack(side="left", padx=8)
        ctk.CTkButton(btn_row, text="关闭", command=self.destroy).pack(side="right")

        ctk.CTkLabel(self, text="生成结果:", anchor="w").pack(
            fill="x", padx=10, pady=(6, 0)
        )
        self._result = ctk.CTkTextbox(self, height=220, state="disabled")
        self._result.pack(fill="both", expand=True, padx=10, pady=(4, 10))

    def _save_config(self) -> None:
        self._config.ai_api_base_url = (
            self._entries["ai_api_base_url"].get().strip()
            or self._config.ai_api_base_url
        )
        self._config.ai_api_key = self._entries["ai_api_key"].get().strip()
        self._config.ai_model = (
            self._entries["ai_model"].get().strip() or self._config.ai_model
        )
        try:
            save_user_config(self._config)
        except Exception:  # noqa: BLE001
            pass
        if self._on_config_saved:
            self._on_config_saved(self._config)

    def _generate(self) -> None:
        self._save_config()
        requirement = self._requirement.get("1.0", "end").strip()
        if not requirement:
            self._append_result("请先输入规则需求\n")
            return
        prompt = build_rules_prompt(requirement)
        base = self._config.ai_api_base_url
        key = self._config.ai_api_key
        model = self._config.ai_model
        self._gen_btn.configure(state="disabled", text="生成中…")
        self._append_result("正在调用 AI 生成规则…\n")

        def worker() -> None:
            try:
                text = asyncio.run(request_rules(base, key, model, prompt))
                rules = parse_ai_rules_response(text)
            except Exception as exc:  # noqa: BLE001
                self.after(0, lambda: self._on_error(str(exc)))
                return
            self.after(0, lambda: self._on_rules_ready(rules))

        threading.Thread(target=worker, daemon=True).start()

    def _on_error(self, message: str) -> None:
        self._gen_btn.configure(state="normal", text="生成规则")
        self._append_result(f"生成失败: {message}\n")

    def _on_rules_ready(self, rules: list[ExpressionRule]) -> None:
        self._generated = rules
        self._gen_btn.configure(state="normal", text="生成规则")
        lines = [f"共 {len(rules)} 条规则:"]
        for r in rules:
            expr = f"{r.left}"
            if r.arith_op:
                expr += f" {r.arith_op} {r.middle}"
            expr += f" {r.op} {r.right}"
            if r.op == "between":
                expr += f" ~ {r.right2}"
            lines.append(
                f"- [{r.id}] {r.label or r.id}: {expr}  权重 {r.weight:g}"
            )
        self._append_result("\n".join(lines) + "\n")

    def _apply(self) -> None:
        if not self._generated:
            self._append_result("没有可追加的规则,请先生成\n")
            return
        self._on_rules(self._generated)
        self._append_result(f"已追加 {len(self._generated)} 条规则\n")

    def _append_result(self, text: str) -> None:
        self._result.configure(state="normal")
        self._result.insert("end", text)
        self._result.configure(state="disabled")
