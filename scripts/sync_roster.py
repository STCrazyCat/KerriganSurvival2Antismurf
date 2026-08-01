#!/usr/bin/env python3
"""Sync or import player roster from CSV/XLSX."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.config.settings import _project_root, load_config
from antismurf.roster.sync.service import RosterSyncService


def write_template(path: Path) -> None:
    from openpyxl import Workbook

    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "玩家名册"
    sheet.append(["玩家名", "句柄", "备注"])
    sheet.append(["示例玩家", "5-S2-1-1234567", "老朋友"])
    workbook.save(path)
    print(f"Template written: {path}")


async def _run(args: argparse.Namespace) -> int:
    config = load_config()
    service = RosterSyncService(config)
    await asyncio.to_thread(service.store.init)

    if args.init_template:
        template = Path(args.init_template)
        if not template.is_absolute():
            template = _project_root() / template
        await asyncio.to_thread(write_template, template)
        return 0

    if args.import_file:
        result = await service.import_file(args.import_file)
    else:
        result = await service.sync_now()

    if result.ok:
        print(f"OK: imported {result.imported} entries", end="")
        if result.pushed:
            print(
                f", pushed +{result.added} new, {result.updated_names} name updates",
                end="",
            )
        print()
        return 0
    print(f"FAILED: {result.error}")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync AntiSmurf player roster")
    parser.add_argument("--import", dest="import_file", help="Import CSV/XLSX file")
    parser.add_argument(
        "--init-template",
        nargs="?",
        const="config/templates/player_roster_template.xlsx",
        help="Write roster Excel template",
    )
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
