from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from antismurf.models.evaluation import MatchSummary
from antismurf.models.rating_profile import PlayerRatingProfile
from antismurf.scoring.handle_rules import RuleHit

VARIABLE_ALIASES: dict[str, str] = {
    "mmr.survivor": "core_mmr.survivor",
    "mmr.kerrigan": "core_mmr.kerrigan",
    "mmr.min": "core_mmr.min",
    "mmr.max": "core_mmr.max",
    "mmr_playlike.survivor": "core_playlike.survivor",
    "mmr_playlike.kerrigan": "core_playlike.kerrigan",
    "mmr_playlike.min": "core_playlike.min",
    "mmr_playlike.max": "core_playlike.max",
}

# Catalog for GUI dropdowns
VARIABLE_CATALOG: dict[str, str] = {
    "handle.profile_id": "玩家句柄（仅末段 profile ID 参与运算）",
    "player.has_team": "是否有战队名（0/1）",
    "mmr.survivor": "生存者核心 MMR",
    "mmr.kerrigan": "凯瑞甘核心 MMR",
    "mmr.min": "核心 MMR 最小值",
    "mmr.max": "核心 MMR 最大值",
    "mmr_playlike.survivor": "生存者反推核心 MMRplaylike",
    "mmr_playlike.kerrigan": "凯瑞甘反推核心 MMRplaylike",
    "mmr_playlike.min": "MMRplaylike 最小值",
    "mmr_playlike.max": "MMRplaylike 最大值",
    "playlike.avg_all": "全局 playlike 均值（未扣 class）",
    "role.mmr": "角色官方 MMR（输入 role.mmr.角色名）",
    "role.playlike": "角色 playlike 均值（输入 role.playlike.角色名）",
    "role.class_mmr": "角色 class MMR 偏移（输入 role.class_mmr.角色名）",
    "core_mmr.kerrigan": "凯瑞甘核心 MMR（同 mmr.kerrigan）",
    "core_mmr.survivor": "生存者核心 MMR（同 mmr.survivor）",
    "core_mmr.max": "核心 MMR 最大值",
    "core_mmr.min": "核心 MMR 最小值",
    "core_playlike.kerrigan": "凯瑞甘反推核心 playlike",
    "core_playlike.survivor": "生存者反推核心 playlike",
    "core_playlike.max": "反推核心 playlike 最大值",
    "core_playlike.min": "反推核心 playlike 最小值",
    "lift.core_max": "playlike 高于核心最大幅度",
    "lift.top3_core_max": "Top3 反推 playlike 均值 − 阵营核心 MMR（取最大）",
    "growth.playlike_recent": "近期 playlike 推断 MMR 增长（近/早窗口差）",
    "spike.count": "playlike 异常高于核心的对局数",
    "spike.max": "单局 playlike 高于核心的最大幅度",
    "data.has_mmr": "有社区 MMR 数据（0/1）",
    "data.has_playlike": "有 playlike 对局数据（0/1）",
    "data.playlike_game_count": "playlike 对局数",
    "data.community_match_count": "社区角色对局总数（各角色 plays 之和）",
    "blocklist.hit": "在黑名单中（0/1）",
    "history.win_rate": "手动战绩胜率",
    "history.win_streak": "手动战绩连胜",
    "history.match_count": "手动战绩场数",
}

VARIABLE_CATEGORIES: dict[str, list[str]] = {
    "玩家信息": [
        "handle.profile_id",
        "player.has_team",
    ],
    "MMR（核心，分阵营）": [
        "mmr.survivor",
        "mmr.kerrigan",
        "mmr.min",
        "mmr.max",
    ],
    "MMRplaylike（反推核心）": [
        "mmr_playlike.survivor",
        "mmr_playlike.kerrigan",
        "mmr_playlike.min",
        "mmr_playlike.max",
        "playlike.avg_all",
    ],
    "MMR（按角色）": [
        "role.mmr",
        "role.playlike",
        "role.class_mmr",
    ],
    "高级 / 扩展": [
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
    ],
}

ARITHMETIC_OPS = ["+", "-", "*", "/"]
ARITHMETIC_LABELS: dict[str, str] = {
    "+": "加 +",
    "-": "减 −",
    "*": "乘 ×",
    "/": "除 ÷",
}

OPERATOR_LABELS: dict[str, str] = {
    ">=": "≥ 大于等于",
    "<=": "≤ 小于等于",
    ">": "> 大于",
    "<": "< 小于",
    "==": "= 等于",
    "!=": "≠ 不等于",
    "between": "介于之间",
    "is_null": "为空",
    "not_null": "不为空",
}

OPERATORS = [
    ">=",
    "<=",
    ">",
    "<",
    "==",
    "!=",
    "between",
    "is_null",
    "not_null",
]


@dataclass
class RuleContext:
    handle: str
    profile_id: int | None
    profile: PlayerRatingProfile | None
    blocklisted: bool = False
    match_history: list[MatchSummary] | None = None
    has_replay_binding: bool = False
    has_team: bool = False
    handle_resolved: bool = True
    handle_ambiguous: bool = False
    handle_candidate_count: int = 1
    handle_constructed: bool = False
    handle_from_binding: bool = False
    ocr_digit_obfuscation: bool = False


def _normalize_variable_path(path: str) -> str:
    path = path.strip()
    return VARIABLE_ALIASES.get(path, path)


def resolve_variable(path: str, ctx: RuleContext) -> Any:
    path = _normalize_variable_path(path.strip())
    profile = ctx.profile
    derived = profile.derived if profile else None

    if path == "handle.profile_id":
        return ctx.profile_id

    if path == "player.has_team":
        return 1 if ctx.has_team else 0

    if path == "handle.resolved":
        return ctx.handle_resolved
    if path == "handle.ambiguous":
        return ctx.handle_ambiguous
    if path == "handle.candidate_count":
        return ctx.handle_candidate_count
    if path == "handle.constructed":
        return ctx.handle_constructed
    if path == "handle.from_binding":
        return ctx.handle_from_binding
    if path == "ocr.digit_obfuscation":
        return ctx.ocr_digit_obfuscation

    if path == "data.has_replay_binding":
        return ctx.has_replay_binding

    if profile and path.startswith("role.mmr."):
        role_name = path[len("role.mmr.") :]
        role = profile.roles.get(role_name)
        return role.mmr if role else None
    if profile and path.startswith("role.class_mmr."):
        role_name = path[len("role.class_mmr.") :]
        role = profile.roles.get(role_name)
        return role.class_mmr if role else None
    if derived and path.startswith("role.playlike."):
        role_name = path[len("role.playlike.") :]
        return derived.playlike_avg_by_role.get(role_name)

    if path == "data.has_replay_binding":
        return ctx.has_replay_binding

    if not derived:
        if path.startswith("data."):
            if path == "data.has_mmr":
                return False
            if path == "data.has_playlike":
                return False
            if path == "data.playlike_game_count":
                return 0
            if path == "data.community_match_count":
                return 0
            if path == "data.has_replay_binding":
                return ctx.has_replay_binding
        return None

    mapping: dict[str, Any] = {
        "core_mmr.kerrigan": derived.core_mmr.kerrigan,
        "core_mmr.survivor": derived.core_mmr.survivor,
        "core_mmr.max": derived.core_mmr.max_value,
        "core_mmr.min": derived.core_mmr.min_value,
        "core_playlike.kerrigan": derived.core_playlike.kerrigan,
        "core_playlike.survivor": derived.core_playlike.survivor,
        "core_playlike.max": derived.core_playlike.max_value,
        "core_playlike.min": derived.core_playlike.min_value,
        "lift.core_kerrigan": derived.lift_core_kerrigan,
        "lift.core_survivor": derived.lift_core_survivor,
        "lift.core_max": derived.lift_core_max,
        "lift.top3_core_max": derived.lift_top3_core_max,
        "growth.playlike_recent": derived.playlike_recent_growth,
        "gap.core_kerrigan": derived.gap_core_kerrigan,
        "gap.core_survivor": derived.gap_core_survivor,
        "gap.core_max": derived.gap_core_max,
        "spike.count": derived.playlike_spike_count,
        "spike.max": derived.playlike_spike_max,
        "spike.avg": derived.playlike_spike_avg,
        "spike.count_survivor": derived.playlike_spike_count_survivor,
        "spike.count_kerrigan": derived.playlike_spike_count_kerrigan,
        "playlike.avg_all": derived.playlike_avg_all,
        "playlike.avg_hunter": derived.playlike_avg_by_archetype.get("hunter"),
        "playlike.avg_defender": derived.playlike_avg_by_archetype.get("defender"),
        "playlike.avg_builder": derived.playlike_avg_by_archetype.get("builder"),
        "playlike.avg_support": derived.playlike_avg_by_archetype.get("support"),
        "playlike.avg_kerrigan": derived.playlike_avg_by_side.get("kerrigan"),
        "playlike.avg_survivor": derived.playlike_avg_by_side.get("survivor"),
        "class_mmr.max_kerrigan": derived.class_mmr_max_by_side.get("kerrigan"),
        "class_mmr.max_survivor": derived.class_mmr_max_by_side.get("survivor"),
        "data.has_mmr": derived.data_quality.has_mmr,
        "data.has_playlike": derived.data_quality.has_playlike,
        "data.playlike_game_count": derived.data_quality.playlike_game_count,
        "data.community_match_count": derived.data_quality.community_match_count,
        "blocklist.hit": ctx.blocklisted,
        "history.win_rate": _history_win_rate(ctx.match_history),
        "history.win_streak": _history_win_streak(ctx.match_history),
        "history.match_count": _history_match_count(ctx.match_history),
    }
    for alias, target in VARIABLE_ALIASES.items():
        if path == alias and target in mapping:
            return mapping[target]
    return mapping.get(path)


def _history_match_count(matches: list[MatchSummary] | None) -> int:
    if not matches:
        return 0
    return len([m for m in matches if m.decision in ("win", "loss")])


def _history_win_rate(matches: list[MatchSummary] | None) -> float | None:
    if not matches:
        return None
    decided = [m for m in matches if m.decision in ("win", "loss")]
    if not decided:
        return None
    wins = sum(1 for m in decided if m.decision == "win")
    return wins / len(decided)


def _history_win_streak(matches: list[MatchSummary] | None) -> int:
    if not matches:
        return 0
    decided = [m for m in matches if m.decision in ("win", "loss")]
    streak = 0
    for m in reversed(decided):
        if m.decision == "win":
            streak += 1
        else:
            break
    return streak


def _is_variable_ref(text: str) -> bool:
    if text in VARIABLE_CATALOG or text in VARIABLE_ALIASES:
        return True
    prefixes = (
        "handle.",
        "player.",
        "data.",
        "mmr.",
        "mmr_playlike.",
        "core_mmr.",
        "core_playlike.",
        "role.mmr.",
        "role.playlike.",
        "role.class_mmr.",
        "lift.",
        "growth.",
        "spike.",
        "playlike.",
        "blocklist.",
        "history.",
        "class_mmr.",
        "gap.",
    )
    return any(text.startswith(prefix) for prefix in prefixes)


def _parse_operand(value: str | float | int | bool, ctx: RuleContext) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text.lower() in ("true", "false"):
        return text.lower() == "true"
    if _is_variable_ref(text):
        return resolve_variable(_normalize_variable_path(text), ctx)
    try:
        return float(text)
    except ValueError:
        return text


def _apply_arithmetic(op: str, left: Any, right: Any) -> float | None:
    if left is None or right is None:
        return None
    try:
        a = float(left)
        b = float(right)
    except (TypeError, ValueError):
        return None
    if op == "+":
        return a + b
    if op == "-":
        return a - b
    if op == "*":
        return a * b
    if op == "/":
        if b == 0:
            return None
        return a / b
    return None


def _compare(op: str, left: Any, right: Any, right2: Any = None) -> bool:
    if op == "is_null":
        return left is None
    if op == "not_null":
        return left is not None
    if left is None:
        return False
    if op == "between":
        if right is None or right2 is None:
            return False
        return float(right) <= float(left) <= float(right2)
    if op == "==":
        if isinstance(left, bool) or isinstance(right, bool):
            return bool(left) == bool(right)
        return float(left) == float(right)
    if op == "!=":
        if isinstance(left, bool) or isinstance(right, bool):
            return bool(left) != bool(right)
        return float(left) != float(right)
    if right is None:
        return False
    lf, rf = float(left), float(right)
    if op == ">=":
        return lf >= rf
    if op == "<=":
        return lf <= rf
    if op == ">":
        return lf > rf
    if op == "<":
        return lf < rf
    return False


def _rule_expression_text(rule: Any) -> str:
    arith_op = str(getattr(rule, "arith_op", "") or "").strip()
    middle = str(getattr(rule, "middle", "") or "").strip()
    if arith_op and middle:
        return f"{rule.left} {arith_op} {middle} {rule.op} {rule.right}"
    return f"{rule.left} {rule.op} {rule.right}"


def evaluate_expression_rule(rule: Any, ctx: RuleContext) -> RuleHit | None:
    if not rule.enabled:
        return None

    min_games = int(getattr(rule, "min_games", 0) or 0)
    if min_games > 0 and ctx.profile:
        count = ctx.profile.derived.data_quality.playlike_game_count
        if count < min_games:
            return None

    left_raw = _parse_operand(rule.left, ctx)
    arith_op = str(getattr(rule, "arith_op", "") or "").strip()
    middle_raw = getattr(rule, "middle", "") or ""
    if arith_op and middle_raw:
        middle_val = _parse_operand(middle_raw, ctx)
        left = _apply_arithmetic(arith_op, left_raw, middle_val)
    else:
        left = left_raw

    right = _parse_operand(rule.right, ctx) if rule.right not in (None, "") else None
    right2 = (
        _parse_operand(rule.right2, ctx)
        if getattr(rule, "right2", None) not in (None, "")
        else None
    )

    if rule.op in ("is_null", "not_null"):
        matched = _compare(rule.op, left, None)
    else:
        matched = _compare(rule.op, left, right, right2)

    weight = rule.weight if matched else getattr(rule, "else_weight", 0)
    if weight == 0:
        return None

    label = rule.label or rule.id
    left_disp = _format_val(left)
    right_disp = _format_val(right)
    expr_text = _rule_expression_text(rule)
    if rule.op in ("is_null", "not_null"):
        reason = f"{label}: {expr_text} ({left_disp})"
    elif rule.op == "between":
        reason = (
            f"{label}: {expr_text} = {left_disp} "
            f"在 {_format_val(right)}~{_format_val(right2)} 之间"
        )
    else:
        reason = f"{label}: {expr_text} = {left_disp} {rule.op} {right_disp}"

    return RuleHit(rule.id, weight, reason)


def _format_val(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if value == int(value):
            return str(int(value))
        return f"{value:.1f}"
    return str(value)


def evaluate_all_expression_rules(rules: list[Any], ctx: RuleContext) -> list[RuleHit]:
    hits: list[RuleHit] = []
    for rule in rules:
        hit = evaluate_expression_rule(rule, ctx)
        if hit:
            hits.append(hit)
    return hits
