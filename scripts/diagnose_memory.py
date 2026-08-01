#!/usr/bin/env python3
"""Inspect local memory scan profile DB and run a one-shot memory read."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.config.settings import load_config
from antismurf.lobby.memory_lobby_reader import MemoryLobbyReader
from antismurf.lobby.memory_profile_store import MemoryProfileStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose SC2 memory scan profile DB")
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Print memory_profile.db statistics only",
    )
    parser.add_argument(
        "--scan",
        action="store_true",
        help="Run one memory lobby snapshot (requires memory.enabled)",
    )
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    store = MemoryProfileStore()
    if args.preview or not args.scan:
        data = store.preview()
        if args.json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(f"DB: {data['db_path']}")
            print(f"Sessions: {data['sessions']}")
            print(f"Handle observations: {data['handle_observations']}")
            print(f"Name bindings: {data['name_bindings']}")
            print(f"Region hints: {data['region_hints']}")
            for item in data.get("top_regions", []):
                print(f"  region {item['base']} hits={item['hits']}")
        if not args.scan:
            return 0

    config = load_config()
    config.memory_enabled = True
    reader = MemoryLobbyReader(config, profile_store=store)
    preview = reader.preview()
    if args.json:
        print(json.dumps(preview, ensure_ascii=False, indent=2))
    else:
        print(f"Scan mode: {preview.get('scan_mode')}")
        print(f"Duration ms: {preview.get('scan_duration_ms')}")
        print(f"Regions: {preview.get('regions_scanned')}")
        print(f"Fallback: {preview.get('fallback_used')}")
        for slot in preview.get("slots", []):
            print(
                f"  {slot.get('handle')} <=> {slot.get('display_name')} "
                f"({slot.get('name_source')})"
            )
        if preview.get("error"):
            print("Error:", preview["error"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
