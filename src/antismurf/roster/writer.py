from __future__ import annotations

import csv
from pathlib import Path


def write_csv_file(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["玩家名", "句柄", "备注"])
        for row in rows:
            writer.writerow(
                [
                    row.get("display_name", ""),
                    row.get("handle", ""),
                    row.get("remark", ""),
                ]
            )


def write_xlsx_file(path: Path, rows: list[dict[str, str]]) -> None:
    from openpyxl import Workbook

    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "玩家名册"
    sheet.append(["玩家名", "句柄", "备注"])
    for row in rows:
        sheet.append(
            [
                row.get("display_name", ""),
                row.get("handle", ""),
                row.get("remark", ""),
            ]
        )
    workbook.save(path)


def write_roster_file(path: str | Path, rows: list[dict[str, str]]) -> None:
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    if suffix == ".csv":
        write_csv_file(file_path, rows)
        return
    if suffix in (".xlsx", ".xlsm", ""):
        target = file_path if suffix else file_path.with_suffix(".xlsx")
        write_xlsx_file(target, rows)
        return
    raise ValueError(f"不支持的名册写入格式: {suffix}")
