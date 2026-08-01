from __future__ import annotations

from typing import Any

from antismurf.config.settings import ExpressionRule

VARIABLE_CATALOG_IDS = {
    "handle.profile_id",
    "player.has_team",
    "mmr.survivor",
    "mmr.kerrigan",
    "mmr.min",
    "mmr.max",
    "mmr_playlike.survivor",
    "mmr_playlike.kerrigan",
    "mmr_playlike.min",
    "mmr_playlike.max",
    "playlike.avg_all",
    "role.mmr",
    "role.playlike",
    "role.class_mmr",
    "core_mmr.kerrigan",
    "core_mmr.survivor",
    "core_mmr.max",
    "core_mmr.min",
    "core_playlike.kerrigan",
    "core_playlike.survivor",
    "core_playlike.max",
    "core_playlike.min",
    "lift.core_max",
    "lift.top3_core_max",
    "growth.playlike_recent",
    "spike.count",
    "spike.max",
    "data.has_mmr",
    "data.has_playlike",
    "data.playlike_game_count",
    "data.community_match_count",
    "blocklist.hit",
    "history.win_rate",
    "history.win_streak",
    "history.match_count",
}


def parse_toml_value(value: Any) -> str | float | bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    return str(value) if value is not None else ""


def format_toml_value(value: str | float | bool) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if value == int(value):
            return str(int(value))
        return str(value)
    text = str(value)
    if text in VARIABLE_CATALOG_IDS:
        return f'"{text}"'
    try:
        float(text)
        return text
    except ValueError:
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'


def expression_rule_from_dict(item: dict[str, Any]) -> ExpressionRule:
    return ExpressionRule(
        id=str(item.get("id", "")),
        enabled=bool(item.get("enabled", True)),
        label=str(item.get("label", item.get("id", ""))),
        left=str(item.get("left", "")),
        arith_op=str(item.get("arith_op", "")),
        middle=str(item.get("middle", "")),
        op=str(item.get("op", ">=")),
        right=parse_toml_value(item.get("right", "")),
        right2=parse_toml_value(item.get("right2", "")),
        weight=float(item.get("weight", 0)),
        else_weight=float(item.get("else_weight", 0)),
        min_games=int(item.get("min_games", 0)),
    )


def expression_rules_from_raw_list(
    raw_rules: list[dict[str, Any]] | None,
) -> list[ExpressionRule]:
    if not raw_rules:
        return []
    result: list[ExpressionRule] = []
    for item in raw_rules:
        if isinstance(item, dict):
            result.append(expression_rule_from_dict(item))
    return result


def format_expression_rule_toml_lines(rule: ExpressionRule) -> list[str]:
    lines = [
        "[[expression_rules]]",
        f'id = "{rule.id}"',
        f"enabled = {'true' if rule.enabled else 'false'}",
        f'label = "{rule.label.replace(chr(92), chr(92)+chr(92)).replace(chr(34), chr(92)+chr(34))}"',
        f'left = "{rule.left}"',
    ]
    if rule.arith_op:
        lines.append(f'arith_op = "{rule.arith_op}"')
    if rule.middle:
        lines.append(f'middle = "{rule.middle}"')
    lines.extend([
        f'op = "{rule.op}"',
        f"right = {format_toml_value(rule.right)}",
    ])
    if rule.right2 not in ("", None):
        lines.append(f"right2 = {format_toml_value(rule.right2)}")
    lines.append(f"weight = {rule.weight}")
    lines.append(f"else_weight = {rule.else_weight}")
    if rule.min_games:
        lines.append(f"min_games = {rule.min_games}")
    lines.append("")
    return lines
