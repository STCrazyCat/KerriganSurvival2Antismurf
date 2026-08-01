import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.config.settings import ExpressionRule
from antismurf.scoring.presets import load_preset_rules
from antismurf.scoring.rule_pack import (
    RulePackMeta,
    export_rule_pack,
    load_rule_pack,
    merge_rules,
    save_rule_pack,
    validate_rules,
)


def test_export_import_roundtrip() -> None:
    rules = [
        ExpressionRule(
            id="test_rule",
            label='含引号"与中文',
            left="gap.core_max",
            op=">=",
            right=500,
            weight=10,
        )
    ]
    meta = RulePackMeta(name="测试包", author="tester")
    text = export_rule_pack(rules, meta)
    path = Path("logs/test_rule_pack.txt")
    path.parent.mkdir(parents=True, exist_ok=True)
    save_rule_pack(path, rules, meta)
    loaded_meta, loaded = load_rule_pack(path)
    assert loaded_meta.name == "测试包"
    assert len(loaded) == 1
    assert loaded[0].id == "test_rule"
    assert loaded[0].label == '含引号"与中文'
    assert "AntiSmurf Rule Pack" in text


def test_validate_rules_rejects_bad_operator() -> None:
    rules = [
        ExpressionRule(
            id="bad",
            left="gap.core_max",
            op="???",
            right=1,
            weight=1,
        )
    ]
    result = validate_rules(rules)
    assert not result.ok


def test_merge_by_id() -> None:
    existing = [ExpressionRule(id="a", weight=1)]
    imported = [ExpressionRule(id="a", weight=9), ExpressionRule(id="b", weight=2)]
    merged = merge_rules(existing, imported, "merge_by_id")
    weights = {rule.id: rule.weight for rule in merged}
    assert weights == {"a": 9.0, "b": 2.0}


def test_preset_compatible() -> None:
    for name in ("balanced", "aggressive", "conservative"):
        raw = load_preset_rules(name)
        rules = [
            ExpressionRule(
                id=str(item.get("id", "")),
                enabled=bool(item.get("enabled", True)),
                label=str(item.get("label", "")),
                left=str(item.get("left", "")),
                op=str(item.get("op", ">=")),
                right=item.get("right", ""),
                right2=item.get("right2", ""),
                weight=float(item.get("weight", 0)),
                else_weight=float(item.get("else_weight", 0)),
                min_games=int(item.get("min_games", 0)),
            )
            for item in raw
        ]
        result = validate_rules(rules)
        assert result.ok, f"{name}: {result.errors}"
