from __future__ import annotations

from collections.abc import Callable

import customtkinter as ctk

from antismurf.scoring.expression_engine import (
    ARITHMETIC_LABELS,
    ARITHMETIC_OPS,
    OPERATOR_LABELS,
    OPERATORS,
    VARIABLE_CATALOG,
    VARIABLE_CATEGORIES,
)


class OperandPicker(ctk.CTkFrame):
    """Category menu + variable/value picker for rule operands."""

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        *,
        label: str,
        allow_variables: bool = True,
        on_change: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self._allow_variables = allow_variables
        self._on_change = on_change
        self._value_var = ctk.StringVar(value="")
        self._category_var = ctk.StringVar(value="")

        ctk.CTkLabel(self, text=label, width=88, anchor="w").pack(side="left")
        self._entry = ctk.CTkEntry(self, width=200, textvariable=self._value_var)
        self._entry.pack(side="left", padx=4)
        self._value_var.trace_add("write", lambda *_: self._notify())

        self._label_to_var: dict[str, str] = {}
        if allow_variables:
            categories = list(VARIABLE_CATEGORIES.keys())
            first = categories[0] if categories else ""
            self._category_var.set(first)
            self._cat_menu = ctk.CTkOptionMenu(
                self,
                width=110,
                variable=self._category_var,
                values=categories,
                command=self._on_category,
            )
            self._cat_menu.pack(side="left", padx=2)
            self._var_menu = ctk.CTkOptionMenu(
                self,
                width=200,
                values=[],
                command=self._pick_variable,
            )
            self._var_menu.pack(side="left", padx=2)
            ctk.CTkButton(
                self, text="插入变量", width=72, command=self._insert_selected_var
            ).pack(side="left", padx=2)
            self._on_category(first)

    def _vars_for_category(self, category: str) -> list[tuple[str, str]]:
        """返回 (中文标签, 变量 key) 列表,下拉只显示中文标签。"""
        ids = VARIABLE_CATEGORIES.get(category, [])
        return [(VARIABLE_CATALOG.get(vid, vid), vid) for vid in ids]

    def _on_category(self, category: str) -> None:
        pairs = self._vars_for_category(category)
        self._label_to_var = dict(pairs)
        values = [label for label, _ in pairs] or ["(无)"]
        self._var_menu.configure(values=values)
        self._var_menu.set(values[0])

    def _pick_variable(self, label: str) -> None:
        self._insert_var(self._label_to_var.get(label, label))

    def _insert_selected_var(self) -> None:
        label = self._var_menu.get()
        if label and label != "(无)":
            self._insert_var(self._label_to_var.get(label, label))

    def _insert_var(self, var_id: str) -> None:
        self._value_var.set(var_id)
        self._notify()

    def _notify(self) -> None:
        if self._on_change:
            self._on_change()

    def get(self) -> str:
        return self._value_var.get().strip()

    def set(self, value: str | float | bool) -> None:
        text = str(value)
        self._value_var.set(text)
        if text in VARIABLE_CATALOG:
            self._sync_menu_to_var(text)

    def _sync_menu_to_var(self, var_id: str) -> None:
        """按变量 key 同步分类菜单与变量下拉(加载已有规则时)。"""
        for category, ids in VARIABLE_CATEGORIES.items():
            if var_id in ids:
                self._category_var.set(category)
                self._on_category(category)
                self._var_menu.set(VARIABLE_CATALOG.get(var_id, var_id))
                return


class OperatorPicker(ctk.CTkFrame):
    def __init__(
        self,
        master: ctk.CTkBaseClass,
        *,
        label: str = "比较运算符",
        operators: list[str] | None = None,
        labels_map: dict[str, str] | None = None,
        on_change: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self._on_change = on_change
        ops = operators or OPERATORS
        lmap = labels_map or OPERATOR_LABELS
        display = [f"{op} — {lmap.get(op, op)}" for op in ops]
        self._op_var = ctk.StringVar(value=display[0] if display else ">=")
        ctk.CTkLabel(self, text=label, width=88, anchor="w").pack(side="left")
        self._menu = ctk.CTkOptionMenu(
            self,
            width=220,
            variable=self._op_var,
            values=display,
            command=lambda _: self._notify(),
        )
        self._menu.pack(side="left", padx=4)

    def _notify(self) -> None:
        if self._on_change:
            self._on_change()

    def get(self) -> str:
        return self._op_var.get().split(" — ", 1)[0].strip()

    def set(self, op: str) -> None:
        for label in self._menu.cget("values"):
            if label.startswith(op):
                self._op_var.set(label)
                return
        self._op_var.set(op)


class ArithmeticPicker(ctk.CTkFrame):
    """Optional + - * / between two operands."""

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        *,
        on_change: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self._on_change = on_change
        options = ["无 — 单操作数"] + [
            f"{op} — {ARITHMETIC_LABELS.get(op, op)}" for op in ARITHMETIC_OPS
        ]
        self._op_var = ctk.StringVar(value=options[0])
        ctk.CTkLabel(self, text="算术运算", width=88, anchor="w").pack(side="left")
        self._menu = ctk.CTkOptionMenu(
            self,
            width=220,
            variable=self._op_var,
            values=options,
            command=lambda _: self._notify(),
        )
        self._menu.pack(side="left", padx=4)

    def _notify(self) -> None:
        if self._on_change:
            self._on_change()

    def get(self) -> str:
        raw = self._op_var.get().split(" — ", 1)[0].strip()
        return "" if raw == "无" else raw

    def set(self, op: str) -> None:
        if not op:
            self._op_var.set("无 — 单操作数")
            return
        for label in self._menu.cget("values"):
            if label.startswith(op):
                self._op_var.set(label)
                return


class ExpressionBuilder(ctk.CTkFrame):
    """Build: 值A [± 值B] 比较 阈值 — 条件为真时计分。"""

    def __init__(
        self,
        master: ctk.CTkBaseClass,
        *,
        on_change: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self._on_change = on_change

        self._left = OperandPicker(self, label="值 A", on_change=self._notify)
        self._left.pack(fill="x", pady=2)
        self._arith = ArithmeticPicker(self, on_change=self._on_arith_change)
        self._arith.pack(fill="x", pady=2)
        self._middle = OperandPicker(self, label="值 B", on_change=self._notify)
        self._middle.pack(fill="x", pady=2)
        self._op = OperatorPicker(self, on_change=self._notify)
        self._op.pack(fill="x", pady=2)
        self._right = OperandPicker(self, label="比较值", on_change=self._notify)
        self._right.pack(fill="x", pady=2)
        self._right2 = OperandPicker(self, label="比较值2", on_change=self._notify)
        self._right2.pack(fill="x", pady=2)

        self._preview = ctk.CTkLabel(
            self,
            text="",
            anchor="w",
            text_color="#9cdcfe",
            wraplength=640,
        )
        self._preview.pack(fill="x", pady=(6, 0))
        self._sync_middle_visibility()

    def _on_arith_change(self, *_args) -> None:
        self._sync_middle_visibility()
        self._notify()

    def _sync_middle_visibility(self) -> None:
        use_middle = bool(self._arith.get())
        if use_middle:
            self._middle.pack(fill="x", pady=2)
        else:
            self._middle.pack_forget()
        op = self._op.get()
        if op == "between":
            self._right2.pack(fill="x", pady=2)
        else:
            self._right2.pack_forget()

    def _notify(self) -> None:
        self._sync_middle_visibility()
        self._update_preview()
        if self._on_change:
            self._on_change()

    def _update_preview(self) -> None:
        op = self._op.get()
        left = self._left.get()
        arith = self._arith.get()
        middle = self._middle.get()
        right = self._right.get()
        right2 = self._right2.get()
        if arith and middle:
            expr = f"{left} {arith} {middle}"
        else:
            expr = left
        if op == "between":
            text = f"当 ({expr}) 介于 {right} 与 {right2} 之间 → 计分"
        elif op in ("is_null", "not_null"):
            text = f"当 ({expr}) {OPERATOR_LABELS.get(op, op)} → 计分"
        else:
            text = f"当 ({expr}) {op} {right} → 计分"
        self._preview.configure(text=text)

    def get_left(self) -> str:
        return self._left.get()

    def get_arith_op(self) -> str:
        return self._arith.get()

    def get_middle(self) -> str:
        return self._middle.get()

    def get_op(self) -> str:
        return self._op.get()

    def get_right(self) -> str:
        return self._right.get()

    def get_right2(self) -> str:
        return self._right2.get()

    def set_expression(
        self,
        left: str,
        op: str,
        right: str | float | bool = "",
        right2: str | float | bool = "",
        *,
        arith_op: str = "",
        middle: str = "",
    ) -> None:
        self._left.set(left)
        self._arith.set(arith_op)
        self._middle.set(middle)
        self._op.set(op)
        self._right.set(right)
        self._right2.set(right2)
        self._sync_middle_visibility()
        self._update_preview()
