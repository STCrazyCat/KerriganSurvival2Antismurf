"""Compare recorded player sightings with live community data."""

from __future__ import annotations

from dataclasses import dataclass, field

from antismurf.storage.sightings import PlayerSightingEntry

METRIC_LABELS: dict[str, str] = {
    "survivor_core": "幸存核心",
    "kerrigan_core": "凯瑞甘核心",
    "survivor_pl_top3": "幸存PL前三",
    "kerrigan_pl_top3": "凯瑞甘PL前三",
    "lift_top3_core_max": "Top3抬升",
    "community_match_count": "社区场次",
    "score": "嫌疑分",
    "mmr": "汇总MMR",
    "mmr_playlike": "汇总PL",
}


@dataclass
class MetricDelta:
    key: str
    label: str
    recorded: float | None
    current: float | None
    delta: float | None
    text: str


@dataclass
class SightingComparison:
    entry: PlayerSightingEntry
    current_snapshot: dict | None
    metric_deltas: list[MetricDelta] = field(default_factory=list)
    summary: str = ""
    fetch_error: str | None = None


def _optional_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_delta_text(
    label: str,
    recorded: float | None,
    current: float | None,
) -> MetricDelta | None:
    if recorded is None and current is None:
        return None
    if recorded is None:
        return MetricDelta(
            key="",
            label=label,
            recorded=None,
            current=current,
            delta=None,
            text=f"{label} 现{_fmt(current)}",
        )
    if current is None:
        return MetricDelta(
            key="",
            label=label,
            recorded=recorded,
            current=None,
            delta=None,
            text=f"{label} 录{_fmt(recorded)}",
        )
    delta = current - recorded
    sign = f"+{delta:.0f}" if delta >= 0 else f"{delta:.0f}"
    return MetricDelta(
        key="",
        label=label,
        recorded=recorded,
        current=current,
        delta=delta,
        text=f"{label} {_fmt(recorded)}→{_fmt(current)} ({sign})",
    )


def _fmt(value: float | None) -> str:
    if value is None:
        return "-"
    if value == int(value):
        return str(int(value))
    return f"{value:.0f}"


def compare_sighting(
    entry: PlayerSightingEntry,
    current_snapshot: dict | None,
    *,
    fetch_error: str | None = None,
) -> SightingComparison:
    recorded = entry.snapshot if hasattr(entry, "snapshot") else {}
    if not recorded and hasattr(entry, "snapshot_json"):
        recorded = entry.snapshot_json  # type: ignore[attr-defined]

    comparison = SightingComparison(
        entry=entry,
        current_snapshot=current_snapshot,
        fetch_error=fetch_error,
    )
    if fetch_error:
        comparison.summary = f"无法对比: {fetch_error}"
        return comparison
    if current_snapshot is None:
        comparison.summary = "无法对比: 未获取到最新社区数据"
        return comparison

    deltas: list[MetricDelta] = []
    for key, label in METRIC_LABELS.items():
        recorded_val = _optional_float(recorded.get(key))
        current_val = _optional_float(current_snapshot.get(key))
        item = _format_delta_text(label, recorded_val, current_val)
        if item is not None:
            item.key = key
            deltas.append(item)

    comparison.metric_deltas = deltas
    if deltas:
        comparison.summary = " · ".join(item.text for item in deltas[:6])
        if len(deltas) > 6:
            comparison.summary += f" · …共 {len(deltas)} 项"
    else:
        comparison.summary = "无可对比数值（记录时与当前均无社区 MMR）"
    return comparison
