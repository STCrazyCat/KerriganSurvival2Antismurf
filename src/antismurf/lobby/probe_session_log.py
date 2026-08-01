"""Structured probe session log — export, CE cross-check, confirmation checklist."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from antismurf.config.settings import _project_root


def parse_hex_address(text: str) -> int | None:
    text = (text or "").strip()
    if not text:
        return None
    if text.lower().startswith("0x"):
        return int(text, 16)
    if any(c in text.lower() for c in "abcdef"):
        return int(text, 16)
    return int(text)


def format_address(address: int | None) -> str:
    if address is None:
        return "-"
    return f"0x{address:X}"


@dataclass
class CeReference:
    name_address: int | None = None
    handle_address: int | None = None

    @classmethod
    def from_text(cls, name_text: str, handle_text: str) -> CeReference:
        return cls(
            name_address=parse_hex_address(name_text),
            handle_address=parse_hex_address(handle_text),
        )


@dataclass
class AddressCompareRow:
    kind: str
    tool_address: int | None
    ce_address: int | None
    delta: int | None
    match: bool
    note: str

    def summary_line(self) -> str:
        flag = "✓" if self.match else "✗"
        tool = format_address(self.tool_address)
        ce = format_address(self.ce_address)
        delta = f" Δ={self.delta:+d}" if self.delta is not None else ""
        return f"{flag} {self.kind}: 工具={tool} CE={ce}{delta} | {self.note}"


@dataclass
class ProbeLogEvent:
    timestamp: str
    mode: str
    event_type: str
    summary: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConfirmationSnapshot:
    """Latest tool state for user-facing verification."""

    updated_at: str
    mode: str
    expected_name: str
    expected_handle: str
    tool_name_address: int | None = None
    tool_handle_address: int | None = None
    tool_name_label: str = ""
    tool_handle_label: str = ""
    confirmed: bool = False
    checklist: list[str] = field(default_factory=list)
    ce_rows: list[AddressCompareRow] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    def status_label(self) -> str:
        if self.confirmed and not self.issues:
            return "已确认 — 与预期一致"
        if self.tool_name_address or self.tool_handle_address:
            return "部分确认 — 请查看对照表"
        return "未确认 — 尚无有效地址"

    def summary_lines(self) -> list[str]:
        lines = [
            f"【确认状态】{self.status_label()}",
            f"更新时间: {self.updated_at}  模式: {self.mode}",
            f"目标: {self.expected_name} / {self.expected_handle}",
            f"工具昵称: {format_address(self.tool_name_address)} {self.tool_name_label}",
            f"工具句柄: {format_address(self.tool_handle_address)} {self.tool_handle_label}",
        ]
        if self.checklist:
            lines.append("--- 检查项 ---")
            lines.extend(f"  {line}" for line in self.checklist)
        if self.ce_rows:
            lines.append("--- CE 对照 ---")
            lines.extend(f"  {row.summary_line()}" for row in self.ce_rows)
        if self.issues:
            lines.append("--- 问题 ---")
            lines.extend(f"  ! {issue}" for issue in self.issues)
        return lines


class ProbeSessionLog:
    """In-memory session log with export and CE comparison."""

    def __init__(self, log_dir: str | Path | None = None) -> None:
        root = _project_root()
        self._log_dir = Path(log_dir or root / "data" / "probe_logs")
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self.events: list[ProbeLogEvent] = []
        self.snapshot: ConfirmationSnapshot | None = None
        self._session_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    @property
    def log_dir(self) -> Path:
        return self._log_dir

    def record(
        self,
        *,
        mode: str,
        event_type: str,
        summary: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.events.append(
            ProbeLogEvent(
                timestamp=datetime.now(timezone.utc).isoformat(),
                mode=mode,
                event_type=event_type,
                summary=summary,
                details=details or {},
            )
        )

    def update_snapshot(
        self,
        *,
        mode: str,
        expected_name: str,
        expected_handle: str,
        tool_name_address: int | None = None,
        tool_handle_address: int | None = None,
        tool_name_label: str = "",
        tool_handle_label: str = "",
        name_live_ok: bool | None = None,
        handle_live_ok: bool | None = None,
        ce_ref: CeReference | None = None,
        extra_checklist: list[str] | None = None,
    ) -> ConfirmationSnapshot:
        checklist: list[str] = list(extra_checklist or [])
        issues: list[str] = []

        if tool_name_address is not None:
            if name_live_ok is True:
                checklist.append(f"昵称地址可读且匹配: {format_address(tool_name_address)}")
            elif name_live_ok is False:
                issues.append(f"昵称地址 {format_address(tool_name_address)} 当前内容不匹配")
            else:
                checklist.append(f"昵称地址已记录: {format_address(tool_name_address)}（未做 live 校验）")
        else:
            issues.append("尚未确定昵称地址")

        if tool_handle_address is not None:
            if handle_live_ok is True:
                checklist.append(f"句柄地址可读且匹配: {format_address(tool_handle_address)}")
            elif handle_live_ok is False:
                issues.append(f"句柄地址 {format_address(tool_handle_address)} 当前内容不匹配")
            else:
                checklist.append(f"句柄地址已记录: {format_address(tool_handle_address)}（未做 live 校验）")
        else:
            issues.append("尚未确定句柄地址")

        ce_rows = compare_with_ce(
            tool_name=tool_name_address,
            tool_handle=tool_handle_address,
            ce_ref=ce_ref,
        )
        for row in ce_rows:
            if not row.match and row.ce_address is not None:
                issues.append(row.note)

        confirmed = (
            tool_name_address is not None
            and tool_handle_address is not None
            and name_live_ok is not False
            and handle_live_ok is not False
            and not any(not row.match for row in ce_rows if row.ce_address is not None)
        )

        self.snapshot = ConfirmationSnapshot(
            updated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            mode=mode,
            expected_name=expected_name,
            expected_handle=expected_handle,
            tool_name_address=tool_name_address,
            tool_handle_address=tool_handle_address,
            tool_name_label=tool_name_label,
            tool_handle_label=tool_handle_label,
            confirmed=confirmed,
            checklist=checklist,
            ce_rows=ce_rows,
            issues=issues,
        )
        self.record(
            mode=mode,
            event_type="snapshot",
            summary=self.snapshot.status_label(),
            details={
                "name": format_address(tool_name_address),
                "handle": format_address(tool_handle_address),
                "confirmed": confirmed,
            },
        )
        return self.snapshot

    def export_json(self, path: str | Path | None = None) -> Path:
        target = Path(path) if path else self._log_dir / f"session_{self._session_id}.json"
        snapshot_data = None
        if self.snapshot:
            snapshot_data = {
                "updated_at": self.snapshot.updated_at,
                "mode": self.snapshot.mode,
                "expected_name": self.snapshot.expected_name,
                "expected_handle": self.snapshot.expected_handle,
                "tool_name_address": format_address(self.snapshot.tool_name_address),
                "tool_handle_address": format_address(self.snapshot.tool_handle_address),
                "confirmed": self.snapshot.confirmed,
                "checklist": self.snapshot.checklist,
                "issues": self.snapshot.issues,
                "ce_rows": [asdict(row) for row in self.snapshot.ce_rows],
            }
        payload = {
            "session_id": self._session_id,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "snapshot": snapshot_data,
            "events": [asdict(event) for event in self.events],
        }
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return target

    def export_text(self, path: str | Path | None = None) -> Path:
        target = Path(path) if path else self._log_dir / f"session_{self._session_id}.txt"
        lines = [f"Probe Session {self._session_id}", ""]
        if self.snapshot:
            lines.extend(self.snapshot.summary_lines())
            lines.append("")
        lines.append("=== 事件记录 ===")
        for event in self.events:
            lines.append(f"[{event.timestamp}] {event.mode}/{event.event_type}: {event.summary}")
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return target


def compare_with_ce(
    *,
    tool_name: int | None,
    tool_handle: int | None,
    ce_ref: CeReference | None,
    tolerance: int = 64,
) -> list[AddressCompareRow]:
    if ce_ref is None:
        return []
    rows: list[AddressCompareRow] = []

    if ce_ref.name_address is not None:
        if tool_name is None:
            rows.append(
                AddressCompareRow(
                    kind="昵称",
                    tool_address=None,
                    ce_address=ce_ref.name_address,
                    delta=None,
                    match=False,
                    note="工具尚未给出昵称地址，无法与 CE 对照",
                )
            )
        else:
            delta = tool_name - ce_ref.name_address
            match = abs(delta) <= tolerance
            rows.append(
                AddressCompareRow(
                    kind="昵称",
                    tool_address=tool_name,
                    ce_address=ce_ref.name_address,
                    delta=delta,
                    match=match,
                    note="地址一致" if match else f"与 CE 相差 {abs(delta)} 字节（容差 {tolerance}）",
                )
            )

    if ce_ref.handle_address is not None:
        if tool_handle is None:
            rows.append(
                AddressCompareRow(
                    kind="句柄",
                    tool_address=None,
                    ce_address=ce_ref.handle_address,
                    delta=None,
                    match=False,
                    note="工具尚未给出句柄地址，无法与 CE 对照",
                )
            )
        else:
            delta = tool_handle - ce_ref.handle_address
            match = abs(delta) <= tolerance
            rows.append(
                AddressCompareRow(
                    kind="句柄",
                    tool_address=tool_handle,
                    ce_address=ce_ref.handle_address,
                    delta=delta,
                    match=match,
                    note="地址一致" if match else f"与 CE 相差 {abs(delta)} 字节（容差 {tolerance}）",
                )
            )
    return rows
