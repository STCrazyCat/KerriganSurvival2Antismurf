import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.config.settings import AppConfig, RuleConfig
from antismurf.scoring.blocklist_rules import evaluate_blocklist


def test_blocklist_rule():
    cfg = AppConfig(
        blocklist_handles={"5-S2-1-9999"},
        rules={"handle_blocklist": RuleConfig(enabled=True, weight=30.0)},
    )
    hits = evaluate_blocklist(cfg, "5-S2-1-9999")
    assert len(hits) == 1
    assert hits[0].rule_id == "handle_blocklist"
