import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.config.settings import ExpressionRule
from antismurf.data.profile_builder import build_profile_from_stub_summary
from antismurf.models.rating_profile import CoreMmrPair, CorePlaylikePair, DerivedMetrics
from antismurf.scoring.expression_engine import RuleContext, evaluate_expression_rule


def _ctx(mmr=5000, playlike=3000, profile_id=20000):
    profile = build_profile_from_stub_summary(
        "5-S2-1-20000",
        {"mmr": mmr, "mmr_playlike": playlike},
    )
    return RuleContext(
        handle="5-S2-1-20000",
        profile_id=profile_id,
        profile=profile,
        blocklisted=False,
    )


def test_expression_arithmetic_subtract():
    profile = build_profile_from_stub_summary(
        "5-S2-1-20000",
        {"mmr": 1600, "mmr_playlike": 2500},
    )
    ctx = RuleContext(
        handle="5-S2-1-20000",
        profile_id=20000,
        profile=profile,
    )
    rule = ExpressionRule(
        id="lift",
        label="MMRplaylike-MMR",
        left="mmr_playlike.max",
        arith_op="-",
        middle="mmr.min",
        op=">",
        right=800,
        weight=80,
    )
    hit = evaluate_expression_rule(rule, ctx)
    assert hit is not None
    assert hit.score_delta == 80


def test_expression_gte_triggers():
    rule = ExpressionRule(
        id="lift",
        label="lift",
        left="lift.core_max",
        op=">=",
        right=500,
        weight=20,
    )
    hit = evaluate_expression_rule(rule, _ctx(mmr=1600, playlike=2500))
    assert hit is not None
    assert hit.score_delta == 20


def test_expression_false_no_hit_when_zero_else_weight():
    rule = ExpressionRule(
        id="low_id",
        label="low",
        left="handle.profile_id",
        op="<",
        right=1000,
        weight=10,
        else_weight=0,
    )
    hit = evaluate_expression_rule(rule, _ctx(profile_id=20000))
    assert hit is None


def test_expression_is_null():
    profile = build_profile_from_stub_summary("5-S2-1-1", {})
    profile.derived = DerivedMetrics(
        core_mmr=CoreMmrPair(),
        core_playlike=CorePlaylikePair(),
    )
    ctx = RuleContext(handle="5-S2-1-1", profile_id=1, profile=profile)
    rule = ExpressionRule(
        id="missing",
        left="core_mmr.max",
        op="is_null",
        weight=5,
    )
    hit = evaluate_expression_rule(rule, ctx)
    assert hit is not None


def test_min_games_blocks_rule():
    rule = ExpressionRule(
        id="pl",
        left="playlike.avg_all",
        op="<=",
        right=2500,
        weight=10,
        min_games=5,
    )
    hit = evaluate_expression_rule(rule, _ctx())
    assert hit is None


def test_handle_profile_id_default_rule():
    rule = ExpressionRule(
        id="handle_profile_id_high",
        left="handle.profile_id",
        op=">",
        right=12500000,
        weight=20,
    )
    hit = evaluate_expression_rule(
        rule,
        RuleContext(handle="5-S2-1-13000000", profile_id=13000000, profile=None),
    )
    assert hit is not None
    assert hit.score_delta == 20


def test_community_match_count_rule() -> None:
    from antismurf.data.profile_builder import build_profile_from_ks2_wiki

    profile = build_profile_from_ks2_wiki(
        "5-S2-1-100",
        {
            "cores": {"kerrigan": 1000, "survivor": 1000},
            "roles_kerrigan": [{"role_name": "A", "plays": 5, "wins": 1}],
        },
    )
    rule = ExpressionRule(
        id="low_games",
        left="data.community_match_count",
        op="<",
        right=10,
        weight=15,
    )
    hit = evaluate_expression_rule(
        rule,
        RuleContext(handle="5-S2-1-100", profile_id=100, profile=profile),
    )
    assert hit is not None
    assert hit.score_delta == 15


def test_missing_replay_binding_rule_triggers_without_profile():
    rule = ExpressionRule(
        id="missing_replay_binding",
        left="data.has_replay_binding",
        op="==",
        right=False,
        weight=12,
    )
    ctx = RuleContext(
        handle="5-S2-1-999",
        profile_id=999,
        profile=None,
        has_replay_binding=False,
    )
    hit = evaluate_expression_rule(rule, ctx)
    assert hit is not None
    assert hit.score_delta == 12


# ---------- 角色占比（playlike 场次） ----------


def _profile_with_playlike(roles_and_dates):
    from antismurf.models.rating_profile import PlaylikeGame

    profile = build_profile_from_stub_summary(
        "5-S2-1-20000", {"mmr": 5000, "mmr_playlike": 3000}
    )
    profile.playlike_games = [
        PlaylikeGame(role=role, date=date) for role, date in roles_and_dates
    ]
    return profile


_DATES = [f"2026-01-{day:02d} 20:00:00" for day in range(1, 11)]


def test_role_share_single_role():
    profile = _profile_with_playlike(
        [("Thakras", _DATES[0]), ("Thakras", _DATES[1]), ("Thakras", _DATES[2]),
         ("Dehaka", _DATES[3]), ("Zagara", _DATES[4])]
    )
    ctx = RuleContext(handle="5-S2-1-20000", profile_id=20000, profile=profile)
    rule = ExpressionRule(
        id="role_share_high",
        label="Thakras 占比高",
        left="role.share.Thakras",
        op=">=",
        right=0.5,
        weight=25,
    )
    hit = evaluate_expression_rule(rule, ctx)
    assert hit is not None
    assert hit.score_delta == 25


def test_role_share_group():
    profile = _profile_with_playlike(
        [("Thakras", _DATES[0]), ("Kerrigan", _DATES[1]), ("Zagara", _DATES[2]),
         ("Dehaka", _DATES[3]), ("Dehaka", _DATES[4])]
    )
    ctx = RuleContext(handle="5-S2-1-20000", profile_id=20000, profile=profile)
    # Thakras+Zagara = 2/5 = 0.4
    rule = ExpressionRule(
        id="role_group_share",
        label="指定角色组占比",
        left="role.share.Thakras,Zagara",
        op=">=",
        right=0.4,
        weight=20,
    )
    hit = evaluate_expression_rule(rule, ctx)
    assert hit is not None
    assert hit.score_delta == 20
    # 占比不足时不触发
    rule2 = ExpressionRule(
        id="role_group_share2",
        left="role.share.Thakras,Zagara",
        op=">=",
        right=0.5,
        weight=20,
    )
    assert evaluate_expression_rule(rule2, ctx) is None


def test_role_share_recent_window():
    # 前 5 场全是 Thakras，后 5 场全是 Dehaka
    games = [("Thakras", d) for d in _DATES[:5]] + [("Dehaka", d) for d in _DATES[5:]]
    profile = _profile_with_playlike(games)
    ctx = RuleContext(handle="5-S2-1-20000", profile_id=20000, profile=profile)
    rule = ExpressionRule(
        id="recent_thakras",
        left="role.share.Thakras",
        op=">=",
        right=0.5,
        weight=20,
    )
    # 默认窗口 20 场 → 占比 0.5，触发
    assert evaluate_expression_rule(rule, ctx) is not None
    # 最近 5 场全是 Dehaka → Thakras 占比 0，不触发
    ctx.playlike_recent_window = 5
    assert evaluate_expression_rule(rule, ctx) is None
    # 最近 10 场 → 占比 0.5，触发
    ctx.playlike_recent_window = 10
    assert evaluate_expression_rule(rule, ctx) is not None


def test_role_share_all_uses_full_history():
    games = [("Thakras", d) for d in _DATES[:5]] + [("Dehaka", d) for d in _DATES[5:]]
    profile = _profile_with_playlike(games)
    ctx = RuleContext(handle="5-S2-1-20000", profile_id=20000, profile=profile)
    # share_all 忽略窗口：全部 10 场中 Thakras 占 0.5
    rule = ExpressionRule(
        id="all_thakras",
        left="role.share_all.Thakras",
        op=">=",
        right=0.5,
        weight=10,
    )
    assert evaluate_expression_rule(rule, ctx) is not None
    # 即便窗口被调小，share_all 依然看全部场次
    ctx.playlike_recent_window = 3
    assert evaluate_expression_rule(rule, ctx) is not None


def test_role_share_no_playlike_data():
    profile = build_profile_from_stub_summary(
        "5-S2-1-20000", {"mmr": 5000, "mmr_playlike": 3000}
    )
    ctx = RuleContext(handle="5-S2-1-20000", profile_id=20000, profile=profile)
    rule = ExpressionRule(
        id="no_data_share",
        left="role.share.Thakras",
        op=">=",
        right=0.5,
        weight=10,
    )
    assert evaluate_expression_rule(rule, ctx) is None


def test_roles_recent_and_total_count():
    profile = _profile_with_playlike(
        [("Thakras", d) for d in _DATES] + [("Dehaka", "2026-02-01 12:00:00")]
    )
    ctx = RuleContext(handle="5-S2-1-20000", profile_id=20000, profile=profile)
    rule = ExpressionRule(
        id="total_count",
        left="roles.total_count",
        op=">=",
        right=11,
        weight=5,
    )
    assert evaluate_expression_rule(rule, ctx) is not None
    ctx.playlike_recent_window = 5
    rule_recent = ExpressionRule(
        id="recent_count",
        left="roles.recent_count",
        op="<=",
        right=5,
        weight=5,
    )
    assert evaluate_expression_rule(rule_recent, ctx) is not None


def test_role_share_alias_normalization():
    # taxonomy 别名匹配：游戏内 "Sir Roachington" 与输入 "Sir_Roachington" 视为同一角色
    profile = _profile_with_playlike(
        [("Sir Roachington", _DATES[0]), ("Sir Roachington", _DATES[1]),
         ("Sir Roachington", _DATES[2]), ("Dehaka", _DATES[3]), ("Dehaka", _DATES[4])]
    )
    ctx = RuleContext(handle="5-S2-1-20000", profile_id=20000, profile=profile)
    rule = ExpressionRule(
        id="alias_share",
        left="role.share.Sir_Roachington",
        op=">=",
        right=0.5,
        weight=15,
    )
    assert evaluate_expression_rule(rule, ctx) is not None
    assert evaluate_expression_rule(rule, ctx).score_delta == 15
