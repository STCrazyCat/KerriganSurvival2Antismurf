from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from antismurf.config.expression_rules_io import (
    expression_rule_from_dict,
    expression_rules_from_raw_list,
    format_expression_rule_toml_lines,
)
from antismurf.config.settings import ExpressionRule
from antismurf.scoring.expression_engine import OPERATORS, VARIABLE_CATALOG

MergeMode = Literal["replace", "merge_by_id"]


@dataclass
class RulePackMeta:
    version: int = 1
    name: str = ""
    author: str = ""
    description: str = ""


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    duplicate_ids: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def load_rule_pack(path: str | Path) -> tuple[RulePackMeta, list[ExpressionRule]]:
    file_path = Path(path)
    with open(file_path, "rb") as f:
        data = tomllib.load(f)

    pack_raw = data.get("pack", {})
    meta = RulePackMeta(
        version=int(pack_raw.get("version", 1)) if isinstance(pack_raw, dict) else 1,
        name=str(pack_raw.get("name", "")) if isinstance(pack_raw, dict) else "",
        author=str(pack_raw.get("author", "")) if isinstance(pack_raw, dict) else "",
        description=str(pack_raw.get("description", ""))
        if isinstance(pack_raw, dict)
        else "",
    )

    raw_rules = data.get("expression_rules")
    if raw_rules is None:
        scoring = data.get("scoring", {})
        if isinstance(scoring, dict):
            raw_rules = scoring.get("expression_rules")

    if not isinstance(raw_rules, list):
        raw_rules = []

    rules = expression_rules_from_raw_list(
        [item for item in raw_rules if isinstance(item, dict)]
    )
    return meta, rules


def export_rule_pack(
    rules: list[ExpressionRule],
    meta: RulePackMeta | None = None,
) -> str:
    pack = meta or RulePackMeta()
    lines = [
        "# AntiSmurf Rule Pack v1",
        "# 分享说明：可用 .txt 扩展名，内容为 TOML",
        "",
        "[pack]",
        f"version = {pack.version}",
        f'name = "{pack.name}"',
        f'author = "{pack.author}"',
        f'description = "{pack.description}"',
        "",
    ]
    for rule in rules:
        lines.extend(format_expression_rule_toml_lines(rule))
    return "\n".join(lines).rstrip() + "\n"


def validate_rules(rules: list[ExpressionRule]) -> ValidationResult:
    result = ValidationResult()
    seen_ids: dict[str, int] = {}

    for index, rule in enumerate(rules):
        prefix = f"规则 #{index + 1}"
        if not rule.id.strip():
            result.errors.append(f"{prefix}: id 不能为空")
            continue

        if rule.id in seen_ids:
            if rule.id not in result.duplicate_ids:
                result.duplicate_ids.append(rule.id)
            result.errors.append(f"{prefix} ({rule.id}): id 重复")
        seen_ids[rule.id] = index

        if rule.left not in VARIABLE_CATALOG:
            result.warnings.append(
                f"{prefix} ({rule.id}): 未知变量 left={rule.left!r}"
            )

        if rule.op not in OPERATORS:
            result.errors.append(f"{prefix} ({rule.id}): 无效运算符 {rule.op!r}")

        if rule.op == "between" and rule.right2 in ("", None):
            result.errors.append(
                f"{prefix} ({rule.id}): between 运算符需要 right2"
            )

    return result


def merge_rules(
    existing: list[ExpressionRule],
    imported: list[ExpressionRule],
    mode: MergeMode,
) -> list[ExpressionRule]:
    if mode == "replace":
        return list(imported)

    merged: dict[str, ExpressionRule] = {rule.id: rule for rule in existing}
    for rule in imported:
        merged[rule.id] = rule
    return list(merged.values())


def save_rule_pack(path: str | Path, rules: list[ExpressionRule], meta: RulePackMeta | None = None) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(export_rule_pack(rules, meta), encoding="utf-8")
    return output
