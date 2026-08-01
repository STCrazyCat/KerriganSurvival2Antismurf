from __future__ import annotations

from antismurf.config.settings import AppConfig, RuleConfig
from antismurf.models.evaluation import MatchSummary
from antismurf.scoring.handle_rules import RuleHit


def _rule(cfg: AppConfig, name: str) -> RuleConfig:
    return cfg.rules.get(name, RuleConfig())


def evaluate_match_history(
    cfg: AppConfig, matches: list[MatchSummary]
) -> list[RuleHit]:
    """Stage-2 rules applied when manual match history is available."""
    hits: list[RuleHit] = []
    if not matches:
        return hits

    decided = [m for m in matches if m.decision in ("win", "loss")]
    if not decided:
        return hits

    wins = sum(1 for m in decided if m.decision == "win")
    win_rate = wins / len(decided)

    domination = _rule(cfg, "history_high_win_rate")
    if domination.enabled and len(decided) >= int(domination.threshold):
        min_rate = 0.85
        if win_rate >= min_rate:
            hits.append(
                RuleHit(
                    "history_high_win_rate",
                    domination.weight,
                    f"近期战绩胜率 {win_rate:.0%}（{wins}/{len(decided)}）",
                )
            )

    streak_rule = _rule(cfg, "history_win_streak")
    if streak_rule.enabled:
        streak = _current_win_streak(decided)
        if streak >= int(streak_rule.threshold):
            hits.append(
                RuleHit(
                    "history_win_streak",
                    streak_rule.weight,
                    f"近期连胜 {streak} 场",
                )
            )

    return hits


def _current_win_streak(matches: list[MatchSummary]) -> int:
    streak = 0
    for m in reversed(matches):
        if m.decision == "win":
            streak += 1
        else:
            break
    return streak
