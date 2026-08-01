#!/usr/bin/env python3
"""Import scoring rules from a shared .txt / .toml rule pack."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.config.settings import load_config, save_user_config
from antismurf.scoring.rule_pack import load_rule_pack, merge_rules, validate_rules


def main() -> int:
    parser = argparse.ArgumentParser(description="Import AntiSmurf rule pack")
    parser.add_argument("--file", required=True, help="Rule pack .txt or .toml path")
    parser.add_argument(
        "--mode",
        choices=["merge", "replace"],
        default="merge",
        help="merge by rule id or replace all rules",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate only")
    args = parser.parse_args()

    meta, imported = load_rule_pack(args.file)
    validation = validate_rules(imported)
    print(f"Pack: {meta.name or Path(args.file).name}")
    print(f"Rules: {len(imported)}")
    for warning in validation.warnings:
        print(f"WARN: {warning}")
    for error in validation.errors:
        print(f"ERROR: {error}")
    if not validation.ok:
        return 1
    if args.dry_run:
        print("Dry run OK")
        return 0

    config = load_config()
    mode = "merge_by_id" if args.mode == "merge" else "replace"
    config.expression_rules = merge_rules(config.expression_rules, imported, mode)
    save_user_config(config)
    print(f"Saved {len(config.expression_rules)} rules to config/user.toml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
