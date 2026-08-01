from __future__ import annotations

import statistics
from datetime import datetime
from typing import Any
from antismurf.data.role_taxonomy import resolve_role
from antismurf.models.player import parse_handle
from antismurf.models.rating_profile import (
    CoreMmrPair,
    CorePlaylikePair,
    DataQuality,
    DerivedMetrics,
    PlaylikeGame,
    PlayerRatingProfile,
    RoleMmr,
)

# Per-game playlike core above faction core MMR counts as a spike (smurf signal).
DEFAULT_PLAYLIKE_SPIKE_THRESHOLD = 400.0


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values))


def _top3_avg(values: list[float]) -> float | None:
    if not values:
        return None
    top = sorted(values, reverse=True)[:3]
    return round(sum(top) / len(top))


def _side_value_map(
    values_by_side: dict[str, list[float]],
    *,
    use_top3: bool,
) -> dict[str, float]:
    out: dict[str, float] = {}
    for side, values in values_by_side.items():
        if not values:
            continue
        avg = _top3_avg(values) if use_top3 else _avg(values)
        if avg is not None:
            out[side] = avg
    return out


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    return round(statistics.median(values))


def build_profile_from_ks2_wiki(
    handle: str,
    mmr_data: dict[str, Any] | None,
    playlike_data: dict[str, Any] | None = None,
    *,
    infer_method: str = "mean",
) -> PlayerRatingProfile:
    _, profile_id = parse_handle(handle)
    profile = PlayerRatingProfile(handle=handle, profile_id=profile_id)

    if mmr_data:
        cores = mmr_data.get("cores") or {}
        profile.core_mmr = CoreMmrPair(
            kerrigan=_float_or_none(cores.get("kerrigan")),
            survivor=_float_or_none(cores.get("survivor")),
        )
        for list_key, default_side in (
            ("roles_kerrigan", "kerrigan"),
            ("roles_survivor", "survivor"),
        ):
            for item in mmr_data.get(list_key) or []:
                if not isinstance(item, dict):
                    continue
                role_name = str(item.get("role_name", ""))
                if not role_name:
                    continue
                tax = resolve_role(
                    role_name,
                    team_name=str(item.get("team_name", "")),
                    team=1 if default_side == "kerrigan" else 0,
                )
                profile.roles[role_name] = RoleMmr(
                    role_name=role_name,
                    core_mmr=_float_or_none(item.get("core_mmr")),
                    class_mmr=_float_or_none(item.get("class_mmr")),
                    mmr=_float_or_none(item.get("mmr")),
                    side=tax.side if tax else default_side,  # type: ignore[arg-type]
                    archetype=tax.archetype if tax else None,
                    wins=int(item.get("wins", 0) or 0),
                    plays=int(item.get("plays", 0) or 0),
                    win_rate=_float_or_none(item.get("win_rate")),
                )

    if playlike_data:
        for game in playlike_data.get("games") or []:
            if not isinstance(game, dict):
                continue
            role_name = str(game.get("role", ""))
            team = game.get("team")
            team_int = int(team) if team is not None else None
            tax = resolve_role(role_name, team=team_int)
            profile.playlike_games.append(
                PlaylikeGame(
                    role=role_name,
                    team=team_int,
                    played_like=_float_or_none(game.get("played_like")),
                    estimated=_float_or_none(game.get("estimated")),
                    date=str(game.get("date", "")),
                    side=tax.side if tax else None,
                    archetype=tax.archetype if tax else None,
                )
            )

    profile.derived = _compute_derived(profile, infer_method=infer_method)
    return profile


def build_profile_from_community_raw(
    handle: str,
    raw: dict[str, Any] | None,
    *,
    infer_method: str = "mean",
) -> PlayerRatingProfile | None:
    if not raw:
        return None
    mmr_data = raw.get("mmr")
    playlike_data = raw.get("played_like")
    if not mmr_data and not playlike_data:
        return build_profile_from_stub_summary(handle, raw)
    return build_profile_from_ks2_wiki(
        handle,
        mmr_data if isinstance(mmr_data, dict) else None,
        playlike_data if isinstance(playlike_data, dict) else None,
        infer_method=infer_method,
    )


def build_profile_from_stub_summary(
    handle: str,
    raw: dict[str, Any],
) -> PlayerRatingProfile:
    """Minimal profile when only flat mmr/mmr_playlike exist (stub mode)."""
    _, profile_id = parse_handle(handle)
    mmr = _float_or_none(raw.get("mmr"))
    playlike = _float_or_none(raw.get("mmr_playlike"))
    profile = PlayerRatingProfile(handle=handle, profile_id=profile_id)
    if mmr is not None:
        profile.core_mmr = CoreMmrPair(kerrigan=mmr, survivor=mmr)
    core_playlike = (
        CorePlaylikePair(kerrigan=playlike, survivor=playlike)
        if playlike is not None
        else CorePlaylikePair()
    )
    derived = DerivedMetrics(
        core_mmr=profile.core_mmr,
        core_playlike=core_playlike,
        playlike_avg_all=playlike,
        data_quality=DataQuality(
            has_mmr=mmr is not None,
            has_playlike=playlike is not None,
            playlike_game_count=0,
        ),
    )
    if mmr is not None and playlike is not None:
        derived.lift_core_kerrigan = playlike - mmr
        derived.lift_core_survivor = playlike - mmr
        derived.lift_core_max = playlike - mmr
        derived.gap_core_kerrigan = mmr - playlike
        derived.gap_core_survivor = mmr - playlike
        derived.gap_core_max = mmr - playlike
    profile.derived = derived
    return profile


def _compute_derived(
    profile: PlayerRatingProfile,
    *,
    infer_method: str = "mean",
    spike_threshold: float = DEFAULT_PLAYLIKE_SPIKE_THRESHOLD,
) -> DerivedMetrics:
    agg = infer_method if infer_method in ("mean", "median") else "mean"
    derived = DerivedMetrics(core_mmr=profile.core_mmr)
    quality = DataQuality(
        has_mmr=profile.core_mmr.kerrigan is not None
        or profile.core_mmr.survivor is not None,
        has_playlike=bool(profile.playlike_games),
        playlike_game_count=len(profile.playlike_games),
    )

    # Class MMR aggregates from official role data
    class_by_side: dict[str, list[float]] = {"kerrigan": [], "survivor": []}
    class_by_arch: dict[str, list[float]] = {}
    for role in profile.roles.values():
        if role.class_mmr is not None and role.side:
            class_by_side.setdefault(role.side, []).append(role.class_mmr)
        if role.class_mmr is not None and role.archetype:
            class_by_arch.setdefault(role.archetype, []).append(role.class_mmr)
        if role.plays:
            quality.community_match_count += int(role.plays)
    derived.class_mmr_max_by_side = {
        side: max(vals) for side, vals in class_by_side.items() if vals
    }
    derived.class_mmr_avg_by_archetype = {
        arch: round(sum(vals) / len(vals), 1)
        for arch, vals in class_by_arch.items()
        if vals
    }

    # Playlike aggregates
    all_pl: list[float] = []
    pl_by_side: dict[str, list[float]] = {}
    pl_by_arch: dict[str, list[float]] = {}
    pl_by_role: dict[str, list[float]] = {}
    for game in profile.playlike_games:
        if game.played_like is None:
            continue
        all_pl.append(game.played_like)
        if game.side:
            pl_by_side.setdefault(game.side, []).append(game.played_like)
        if game.archetype:
            pl_by_arch.setdefault(game.archetype, []).append(game.played_like)
        if game.role:
            pl_by_role.setdefault(game.role, []).append(game.played_like)
    derived.playlike_avg_all = _avg(all_pl)
    derived.playlike_avg_by_side = {k: _avg(v) or 0 for k, v in pl_by_side.items()}
    derived.playlike_avg_by_archetype = {k: _avg(v) or 0 for k, v in pl_by_arch.items()}
    derived.playlike_avg_by_role = {k: _avg(v) or 0 for k, v in pl_by_role.items()}

    # Infer core playlike per game and detect spikes above faction core MMR
    arch_class_avg: dict[str, float] = derived.class_mmr_avg_by_archetype
    inferred_k: list[float] = []
    inferred_s: list[float] = []
    spike_lifts: list[float] = []
    spike_survivor = 0
    spike_kerrigan = 0
    for game in profile.playlike_games:
        if game.played_like is None:
            continue
        class_offset = _lookup_class_offset(profile, game, arch_class_avg)
        side = game.side or _infer_side_from_role(profile, game.role)
        core_for_side = None
        if side == "kerrigan":
            core_for_side = profile.core_mmr.kerrigan
        elif side == "survivor":
            core_for_side = profile.core_mmr.survivor

        if class_offset is None:
            quality.missing_class_offset_count += 1
            if core_for_side is not None:
                lift = game.played_like - core_for_side
                game.lift_over_core = round(lift, 2)
                if lift >= spike_threshold:
                    spike_lifts.append(lift)
                    if side == "survivor":
                        spike_survivor += 1
                    elif side == "kerrigan":
                        spike_kerrigan += 1
            continue

        inferred = game.played_like - class_offset
        game.inferred_core = round(inferred, 2)
        if core_for_side is not None:
            lift = inferred - core_for_side
            game.lift_over_core = round(lift, 2)
            if lift >= spike_threshold:
                spike_lifts.append(lift)
                if side == "survivor":
                    spike_survivor += 1
                elif side == "kerrigan":
                    spike_kerrigan += 1

        if side == "kerrigan":
            inferred_k.append(inferred)
            quality.inferred_kerrigan_games += 1
        elif side == "survivor":
            inferred_s.append(inferred)
            quality.inferred_survivor_games += 1

    combine = _avg if agg == "mean" else _median
    derived.core_playlike = CorePlaylikePair(
        kerrigan=combine(inferred_k),
        survivor=combine(inferred_s),
    )

    role_mmr_by_side: dict[str, list[float]] = {}
    for role in profile.roles.values():
        if role.mmr is None or not role.side:
            continue
        if role.plays <= 0 and not (role.class_mmr and role.class_mmr != 0):
            continue
        role_mmr_by_side.setdefault(role.side, []).append(role.mmr)
    inferred_by_side = {
        "kerrigan": inferred_k,
        "survivor": inferred_s,
    }
    derived.role_mmr_top3_avg_by_side = _side_value_map(role_mmr_by_side, use_top3=True)
    derived.role_mmr_avg_by_side = _side_value_map(role_mmr_by_side, use_top3=False)
    derived.playlike_inferred_top3_avg_by_side = _side_value_map(
        inferred_by_side,
        use_top3=True,
    )
    derived.playlike_inferred_avg_by_side = _side_value_map(
        inferred_by_side,
        use_top3=False,
    )

    derived.playlike_spike_count = len(spike_lifts)
    derived.playlike_spike_max = round(max(spike_lifts), 1) if spike_lifts else None
    derived.playlike_spike_avg = _avg(spike_lifts)
    derived.playlike_spike_count_survivor = spike_survivor
    derived.playlike_spike_count_kerrigan = spike_kerrigan
    derived.data_quality = quality

    if profile.core_mmr.kerrigan is not None and derived.core_playlike.kerrigan is not None:
        derived.lift_core_kerrigan = round(
            derived.core_playlike.kerrigan - profile.core_mmr.kerrigan, 1
        )
        derived.gap_core_kerrigan = round(
            profile.core_mmr.kerrigan - derived.core_playlike.kerrigan, 1
        )
    if profile.core_mmr.survivor is not None and derived.core_playlike.survivor is not None:
        derived.lift_core_survivor = round(
            derived.core_playlike.survivor - profile.core_mmr.survivor, 1
        )
        derived.gap_core_survivor = round(
            profile.core_mmr.survivor - derived.core_playlike.survivor, 1
        )
    lifts = [
        g
        for g in (
            derived.lift_core_kerrigan,
            derived.lift_core_survivor,
        )
        if g is not None
    ]
    if lifts:
        derived.lift_core_max = max(lifts)
    gaps = [g for g in (derived.gap_core_kerrigan, derived.gap_core_survivor) if g is not None]
    if gaps:
        derived.gap_core_max = max(gaps)
    elif profile.core_mmr.max_value is not None and derived.playlike_avg_all is not None:
        derived.lift_core_max = round(
            derived.playlike_avg_all - profile.core_mmr.max_value, 1
        )
        derived.gap_core_max = round(
            profile.core_mmr.max_value - derived.playlike_avg_all, 1
        )

    top3_lifts: list[float] = []
    for side in ("kerrigan", "survivor"):
        top3 = derived.playlike_inferred_top3_avg_by_side.get(side)
        core = getattr(profile.core_mmr, side, None)
        if top3 is not None and core is not None:
            top3_lifts.append(top3 - core)
    if top3_lifts:
        derived.lift_top3_core_max = round(max(top3_lifts), 1)

    derived.playlike_recent_growth = _compute_playlike_recent_growth(profile)

    return derived


def _parse_game_date(value: str) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _compute_playlike_recent_growth(profile: PlayerRatingProfile) -> float | None:
    """Estimate recent MMR growth from playlike timeline (no historical MMR API)."""
    by_side: dict[str, list[tuple[datetime, float]]] = {}
    for game in profile.playlike_games:
        if game.inferred_core is None:
            continue
        dt = _parse_game_date(game.date)
        if dt is None:
            continue
        side = game.side or _infer_side_from_role(profile, game.role)
        if not side:
            continue
        by_side.setdefault(side, []).append((dt, float(game.inferred_core)))

    growths: list[float] = []
    for items in by_side.values():
        if len(items) < 4:
            continue
        items.sort(key=lambda item: item[0])
        window = min(5, max(2, len(items) // 2))
        early = [value for _, value in items[:window]]
        recent = [value for _, value in items[-window:]]
        growths.append(sum(recent) / len(recent) - sum(early) / len(early))
    if not growths:
        return None
    return round(max(growths), 1)


def _lookup_class_offset(
    profile: PlayerRatingProfile,
    game: PlaylikeGame,
    arch_class_avg: dict[str, float],
) -> float | None:
    role = profile.roles.get(game.role)
    if role and role.class_mmr is not None:
        return role.class_mmr
    if game.archetype and game.archetype in arch_class_avg:
        return arch_class_avg[game.archetype]
    tax = resolve_role(game.role, team=game.team)
    if tax and tax.archetype in arch_class_avg:
        return arch_class_avg[tax.archetype]
    return None


def _infer_side_from_role(profile: PlayerRatingProfile, role_name: str) -> str | None:
    role = profile.roles.get(role_name)
    if role and role.side:
        return role.side
    tax = resolve_role(role_name)
    return tax.side if tax else None


def summary_from_profile(profile: PlayerRatingProfile) -> tuple[float | None, float | None]:
    """Flat summary: min faction core MMR + global playlike average."""
    mmr = profile.core_mmr.min_value
    return mmr, profile.summary_playlike
