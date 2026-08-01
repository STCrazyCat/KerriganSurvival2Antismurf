import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.config.settings import load_config
from antismurf.models.evaluation import MatchSummary
from antismurf.scoring.match_rules import evaluate_match_history


def test_history_high_win_rate():
    cfg = load_config()
    matches = [
        MatchSummary(map_name="m", game_type="1v1", decision="win"),
        MatchSummary(map_name="m", game_type="1v1", decision="win"),
        MatchSummary(map_name="m", game_type="1v1", decision="win"),
        MatchSummary(map_name="m", game_type="1v1", decision="win"),
        MatchSummary(map_name="m", game_type="1v1", decision="win"),
    ]
    hits = evaluate_match_history(cfg, matches)
    assert any(h.rule_id == "history_high_win_rate" for h in hits)


def test_history_win_streak():
    cfg = load_config()
    matches = [
        MatchSummary(decision="loss"),
        MatchSummary(decision="win"),
        MatchSummary(decision="win"),
        MatchSummary(decision="win"),
        MatchSummary(decision="win"),
    ]
    hits = evaluate_match_history(cfg, matches)
    assert any(h.rule_id == "history_win_streak" for h in hits)
