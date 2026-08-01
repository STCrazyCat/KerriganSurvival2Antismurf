from __future__ import annotations

from dataclasses import dataclass

from antismurf.config.settings import AppConfig, RuleConfig
from antismurf.models.community import CommunityRating
from antismurf.models.evaluation import Stage1Result
from antismurf.models.player import SuspicionTier, parse_handle


@dataclass
class RuleHit:
    rule_id: str
    score_delta: float
    reason: str


def _rule(cfg: AppConfig, name: str) -> RuleConfig:
    return cfg.rules.get(name, RuleConfig())


def evaluate_handle_discriminator(
    cfg: AppConfig, discriminator: int | None
) -> list[RuleHit]:
    hits: list[RuleHit] = []
    if discriminator is None:
        return hits

    high = _rule(cfg, "handle_discriminator_high")
    if high.enabled and discriminator >= high.threshold:
        hits.append(
            RuleHit(
                "handle_discriminator_high",
                high.weight,
                f"玩家 ID {discriminator} >= {int(high.threshold)}，疑似新账号",
            )
        )

    low = _rule(cfg, "handle_discriminator_low")
    if low.enabled and discriminator < low.threshold:
        hits.append(
            RuleHit(
                "handle_discriminator_low",
                low.weight,
                f"玩家 ID {discriminator} < {int(low.threshold)}，老账号倾向",
            )
        )
    return hits


def evaluate_community(cfg: AppConfig, rating: CommunityRating) -> list[RuleHit]:
    hits: list[RuleHit] = []

    if not rating.has_data:
        missing = _rule(cfg, "missing_community_data")
        if missing.enabled:
            hits.append(
                RuleHit(
                    "missing_community_data",
                    missing.weight,
                    "社区无 MMR 数据",
                )
            )
        return hits

    profile = rating.profile
    derived = profile.derived if profile else None

    spike_rule = _rule(cfg, "playlike_spike_count")
    if spike_rule.enabled and derived and derived.playlike_spike_count >= int(
        spike_rule.threshold
    ):
        hits.append(
            RuleHit(
                "playlike_spike_count",
                spike_rule.weight,
                f"playlike 异常高于核心 {derived.playlike_spike_count} 局 "
                f">= {int(spike_rule.threshold)}",
            )
        )

    spike_max_rule = _rule(cfg, "playlike_spike_magnitude")
    if (
        spike_max_rule.enabled
        and derived
        and derived.playlike_spike_max is not None
        and derived.playlike_spike_max >= spike_max_rule.threshold
    ):
        hits.append(
            RuleHit(
                "playlike_spike_magnitude",
                spike_max_rule.weight,
                f"单局 playlike 超出核心 {derived.playlike_spike_max:.0f} "
                f">= {spike_max_rule.threshold:.0f}",
            )
        )

    lift_rule = _rule(cfg, "playlike_lift_avg")
    if (
        lift_rule.enabled
        and derived
        and derived.lift_core_max is not None
        and derived.lift_core_max >= lift_rule.threshold
    ):
        hits.append(
            RuleHit(
                "playlike_lift_avg",
                lift_rule.weight,
                f"playlike 高于核心幅度 {derived.lift_core_max:.0f} "
                f">= {lift_rule.threshold:.0f}",
            )
        )
    return hits


def score_to_tier(cfg: AppConfig, score: float) -> SuspicionTier:
    if score >= cfg.tier_critical:
        return "critical"
    if score >= cfg.tier_high:
        return "high"
    if score >= cfg.tier_medium:
        return "medium"
    return "low"
