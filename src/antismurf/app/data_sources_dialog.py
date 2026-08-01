from __future__ import annotations



import asyncio

import threading

from pathlib import Path

from tkinter import filedialog

from typing import TYPE_CHECKING, Callable



import customtkinter as ctk



from antismurf.config.settings import AppConfig, save_user_config



if TYPE_CHECKING:

    from antismurf.app.orchestrator import Orchestrator





class DataSourcesDialog(ctk.CTkToplevel):

    """Confirm optional replay upload folder and external rule pack."""



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

        self.title("数据源确认")

        self.geometry("560x420")

        self._config = config

        self._orchestrator = orchestrator

        self._loop = loop

        self._on_saved = on_saved



        scroll = ctk.CTkScrollableFrame(self, label_text="路径")

        scroll.pack(fill="both", expand=True, padx=10, pady=10)



        self._status = ctk.CTkLabel(scroll, text="", anchor="w", text_color="#b08900")

        self._status.pack(fill="x", pady=(0, 8))



        self._replay_path = self._add_path_row(

            scroll,

            "录像目录（自动上传）",

            config.replays_paths[0] if config.replays_paths else "",

            is_dir=True,

        )

        self._rules_path = self._add_path_row(

            scroll,

            "规则包 (.txt/.toml)",

            config.rules_pack_path,

        )



        ctk.CTkLabel(

            scroll,

            text="留空录像目录时，程序会按本机句柄自动搜索 StarCraft II/Replays。\n"

            "规则包可选；也可直接在「评分规则」编辑器中配置。",

            anchor="w",

            wraplength=480,

            text_color="#9cdcfe",

        ).pack(fill="x", padx=4, pady=(8, 6))



        if config.data_sources_confirmed:

            self._status.configure(text="✓ 数据源已确认", text_color="#2d6a4f")

        else:

            self._status.configure(text="填写后点击「确认并启用」", text_color="#b08900")



        btn_row = ctk.CTkFrame(self, fg_color="transparent")

        btn_row.pack(fill="x", padx=12, pady=12)

        ctk.CTkButton(btn_row, text="测试", width=80, command=self._test).pack(

            side="left", padx=4

        )

        ctk.CTkButton(

            btn_row,

            text="确认并启用",

            width=120,

            fg_color="#2d6a4f",

            command=self._confirm,

        ).pack(side="right", padx=4)

        ctk.CTkButton(btn_row, text="保存草稿", width=100, command=self._save_draft).pack(

            side="right", padx=4

        )



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

        ctk.CTkLabel(row, text=label, width=140, anchor="w").pack(side="left")

        entry = ctk.CTkEntry(row, width=320)

        entry.insert(0, value)

        entry.pack(side="left", padx=6)



        def browse() -> None:

            if is_dir:

                path = filedialog.askdirectory(parent=self, title=label)

            else:

                path = filedialog.askopenfilename(

                    parent=self,

                    title=label,

                    filetypes=[

                        ("规则", "*.txt *.toml"),

                        ("所有文件", "*.*"),

                    ],

                )

            if path:

                entry.delete(0, "end")

                entry.insert(0, path)



        ctk.CTkButton(row, text="浏览", width=60, command=browse).pack(side="left")

        return entry



    def _apply_form_to_config(self, *, confirmed: bool) -> AppConfig:

        cfg = self._config

        replay_dir = self._replay_path.get().strip()

        cfg.replays_paths = [replay_dir] if replay_dir else []

        cfg.rules_pack_path = self._rules_path.get().strip()

        if confirmed:

            cfg.data_sources_confirmed = True

        return cfg



    def _save_draft(self) -> None:

        cfg = self._apply_form_to_config(confirmed=False)

        save_user_config(cfg)

        self._config = cfg

        if self._on_saved:

            self._on_saved(cfg)

        self._status.configure(text="草稿已保存（尚未确认启用）", text_color="#b08900")



    def _test(self) -> None:

        errors: list[str] = []

        replay_dir = self._replay_path.get().strip()

        if replay_dir and not Path(replay_dir).is_dir():

            errors.append(f"录像目录不存在: {replay_dir}")

        rules_path = self._rules_path.get().strip()

        if rules_path and not Path(rules_path).is_file():

            errors.append(f"规则包不存在: {rules_path}")

        elif rules_path:

            try:

                from antismurf.scoring.rule_pack import load_rule_pack



                _, rules = load_rule_pack(rules_path)

                if not rules:

                    errors.append("规则包未包含 expression_rules")

            except Exception as exc:

                errors.append(f"规则包解析失败: {exc}")

        if errors:

            self._status.configure(text="; ".join(errors), text_color="#d00000")

        else:

            self._status.configure(text="路径测试通过", text_color="#2d6a4f")



    def _confirm(self) -> None:

        self._test()

        cfg = self._apply_form_to_config(confirmed=True)

        rule_err: str | None = None

        if cfg.rules_pack_path and self._orchestrator:

            rule_err = self._orchestrator.reload_rules_pack()

        save_user_config(cfg)

        self._config = cfg

        if self._on_saved:

            self._on_saved(cfg)

        msg = "已确认并启用数据源"

        if rule_err:

            msg += f"（规则包: {rule_err}）"

        self._status.configure(text=msg, text_color="#2d6a4f")


