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
