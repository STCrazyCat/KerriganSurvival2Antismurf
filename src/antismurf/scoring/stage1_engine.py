from __future__ import annotations

from antismurf.config.settings import AppConfig
from antismurf.data.profile_builder import (
    build_profile_from_community_raw,
    build_profile_from_stub_summary,
)
from antismurf.models.community import CommunityRating
from antismurf.models.evaluation import MatchSummary, Stage1Result
from antismurf.models.player import parse_handle
from antismurf.scoring.expression_engine import RuleContext, evaluate_all_expression_rules
from antismurf.scoring.handle_rules import RuleHit, score_to_tier


class Stage1Engine:
    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def evaluate(
        self,
        handle: str,
        slot_index: int,
        community: CommunityRating,
        match_history: list[MatchSummary] | None = None,
        *,
        blocklisted: bool = False,
        has_replay_binding: bool = False,
        has_team: bool = False,
        handle_resolved: bool = True,
        handle_ambiguous: bool = False,
        handle_candidate_count: int = 1,
        handle_constructed: bool = False,
        handle_from_binding: bool = False,
        ocr_digit_obfuscation: bool = False,
        kerrigan_same_match_spike_count: int = 0,
    ) -> Stage1Result:
        _, discriminator = parse_handle(handle)
        profile = community.profile
        if profile is None:
            profile = build_profile_from_community_raw(handle, community.raw)
        if profile is None or not profile.derived.data_quality.has_mmr:
            if community.mmr is not None or community.mmr_playlike is not None:
                profile = build_profile_from_stub_summary(
                    handle,
                    {
                        "mmr": community.mmr,
                        "mmr_playlike": community.mmr_playlike,
                        **(community.raw or {}),
                    },
                )
        if profile is None:
            from antismurf.models.rating_profile import PlayerRatingProfile

            profile = PlayerRatingProfile(handle=handle, profile_id=discriminator)

        ctx = RuleContext(
            handle=handle,
            profile_id=discriminator,
            profile=profile,
            blocklisted=blocklisted,
            match_history=match_history,
            has_replay_binding=has_replay_binding,
            has_team=has_team,
            handle_resolved=handle_resolved,
            handle_ambiguous=handle_ambiguous,
            handle_candidate_count=handle_candidate_count,
            handle_constructed=handle_constructed,
            handle_from_binding=handle_from_binding,
            ocr_digit_obfuscation=ocr_digit_obfuscation,
        )
        hits = evaluate_all_expression_rules(self._config.expression_rules, ctx)
        hits.extend(self._evaluate_handle_mark_rules(handle))
        hits.extend(self._evaluate_handle_trust_rules(handle))
        if kerrigan_same_match_spike_count > 0:
            per = self._config.same_match_kerrigan_spike_score
            hits.append(
                RuleHit(
                    rule_id="same_match_kerrigan_spike",
                    score_delta=per * kerrigan_same_match_spike_count,
                    reason=(
                        f"与主机同局时凯瑞甘MMR异常升高 "
                        f"({kerrigan_same_match_spike_count}次, +{per:.0f}/次)"
                    ),
                )
            )

        raw_score = sum(h.score_delta for h in hits)
        score = max(0.0, min(100.0, raw_score))
        tier = score_to_tier(self._config, score)

        if community.profile is None:
            community.profile = profile

        return Stage1Result(
            handle=handle,
            slot_index=slot_index,
            tier=tier,
            score=score,
            triggered_rules=[h.rule_id for h in hits],
            rule_reasons=[h.reason for h in hits],
            community=community,
            handle_discriminator=discriminator,
        )

    def should_auto_kick(self, result: Stage1Result) -> bool:
        from antismurf.build_meta import AUTO_KICK_ENABLED

        if not AUTO_KICK_ENABLED:
            return False
        if self._config.dry_run or not self._config.auto_kick_enabled:
            return False
        return result.score >= self._config.kick_threshold

    def _evaluate_handle_mark_rules(self, handle: str) -> list[RuleHit]:
        hits: list[RuleHit] = []
        for mark in self._config.handle_mark_rules:
            if not mark.enabled or mark.handle != handle:
                continue
            label = mark.label or f"手动标记句柄 {handle}"
            hits.append(
                RuleHit(
                    rule_id=f"handle_mark:{handle}",
                    score_delta=mark.weight,
                    reason=f"{label} (+{mark.weight:.0f})",
                )
            )
        return hits

    def _evaluate_handle_trust_rules(self, handle: str) -> list[RuleHit]:
        hits: list[RuleHit] = []
        for rule in self._config.handle_trust_rules:
            if not rule.enabled or rule.handle != handle:
                continue
            label = rule.label or f"信任白名单 {handle}"
            hits.append(
                RuleHit(
                    rule_id=f"handle_trust:{handle}",
                    score_delta=rule.weight,
                    reason=f"{label} ({rule.weight:+.0f})",
                )
            )
        return hits
