from __future__ import annotations

from antismurf.config.settings import AppConfig, RuleConfig
from antismurf.scoring.handle_rules import RuleHit


def evaluate_blocklist(cfg: AppConfig, handle: str) -> list[RuleHit]:
    hits: list[RuleHit] = []
    if handle not in cfg.blocklist_handles:
        return hits
    rule = cfg.rules.get("handle_blocklist", RuleConfig(weight=30.0))
    if not rule.enabled:
        return hits
    hits.append(
        RuleHit(
            "handle_blocklist",
            rule.weight,
            "句柄在黑名单中",
        )
    )
    return hits
