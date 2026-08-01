"""Evaluate scoring rules against labeled handles (placeholder for calibration)."""
from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.community.factory import create_community_provider
from antismurf.config.settings import AppConfig, load_config
from antismurf.scoring.presets import load_preset_rules
from antismurf.scoring.stage1_engine import Stage1Engine


async def _eval_row(engine: Stage1Engine, provider, handle: str, is_smurf: bool):
    community = await provider.get_rating_by_handle(handle)
    result = engine.evaluate(handle, 0, community)
    flagged = result.tier in ("high", "critical")
    return is_smurf, flagged


async def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate scoring rules on labeled data")
    parser.add_argument("--labels", required=True, help="CSV: handle,is_smurf")
    parser.add_argument("--preset", default="balanced")
    args = parser.parse_args()

    cfg = load_config()
    raw = load_preset_rules(args.preset)
    cfg.expression_rules = [
        __import__("antismurf.config.settings", fromlist=["ExpressionRule"]).ExpressionRule(
            id=str(r["id"]),
            enabled=bool(r.get("enabled", True)),
            label=str(r.get("label", r["id"])),
            left=str(r.get("left", "")),
            op=str(r.get("op", ">=")),
            right=r.get("right", ""),
            weight=float(r.get("weight", 0)),
            else_weight=float(r.get("else_weight", 0)),
            min_games=int(r.get("min_games", 0)),
        )
        for r in raw
    ]
    engine = Stage1Engine(cfg)
    provider = create_community_provider(cfg)

    tp = fp = tn = fn = 0
    with open(args.labels, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            is_smurf = row.get("is_smurf", "0").strip() in ("1", "true", "yes")
            handle = row["handle"].strip()
            smurf, flagged = await _eval_row(engine, provider, handle, is_smurf)
            if smurf and flagged:
                tp += 1
            elif smurf and not flagged:
                fn += 1
            elif not smurf and flagged:
                fp += 1
            else:
                tn += 1

    total_smurf = tp + fn
    total_normal = fp + tn
    recall = tp / total_smurf if total_smurf else 0
    fpr = fp / total_normal if total_normal else 0
    print(f"Preset: {args.preset}")
    print(f"Recall: {recall:.1%} ({tp}/{total_smurf})")
    print(f"False positive rate: {fpr:.1%} ({fp}/{total_normal})")


if __name__ == "__main__":
    asyncio.run(main())
