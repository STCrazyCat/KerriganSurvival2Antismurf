"""Mode 4: production-like monitoring using a saved calibration profile."""

from __future__ import annotations

import time
from dataclasses import dataclass

from antismurf.lobby.memory_probe import build_module_map, locate_address
from antismurf.lobby.probe_calibration import (
    CalibratedProfile,
    LiveProfileReading,
    read_profile_live,
)


@dataclass
class CalibratedTickResult:
    tick: int
    elapsed_sec: float
    reading: LiveProfileReading
    name_module: str
    handle_module: str
    status: str  # ok | name_fail | handle_fail | both_fail
    consecutive_ok: int = 0
    consecutive_fail: int = 0

    def summary_line(self) -> str:
        flag = "✓" if self.reading.all_ok else "✗"
        return (
            f"{flag} #{self.tick} [{self.status}] "
            f"昵称@{self.reading.name.address:#x} "
            f"句柄@{self.reading.handle.address:#x} "
            f"连续OK={self.consecutive_ok} 连续FAIL={self.consecutive_fail}"
        )


@dataclass
class CalibratedMonitorStats:
    ticks: int = 0
    ok_ticks: int = 0
    fail_ticks: int = 0
    first_ok_at: float | None = None
    last_fail_at: float | None = None

    def success_rate(self) -> float:
        if self.ticks == 0:
            return 0.0
        return self.ok_ticks / self.ticks


class CalibratedMonitorSession:
    """Poll fixed calibrated addresses — no full memory scan."""

    def __init__(
        self,
        process_handle,
        *,
        pid: int,
        profile: CalibratedProfile,
    ) -> None:
        self._process = process_handle
        self._pid = pid
        self.profile = profile
        self.started_at = time.time()
        self._tick = 0
        self._consecutive_ok = 0
        self._consecutive_fail = 0
        self.stats = CalibratedMonitorStats()
        self.history: list[CalibratedTickResult] = []

    def tick(self) -> CalibratedTickResult:
        self._tick += 1
        modules = build_module_map(self._pid)
        reading = read_profile_live(self._process, self.profile)
        name_loc = locate_address(
            reading.name.address,
            modules=modules,
            process_handle=self._process,
        )
        handle_loc = locate_address(
            reading.handle.address,
            modules=modules,
            process_handle=self._process,
        )

        if reading.all_ok:
            self._consecutive_ok += 1
            self._consecutive_fail = 0
            self.stats.ok_ticks += 1
            if self.stats.first_ok_at is None:
                self.stats.first_ok_at = time.time()
            status = "ok"
        else:
            self._consecutive_fail += 1
            self._consecutive_ok = 0
            self.stats.fail_ticks += 1
            self.stats.last_fail_at = time.time()
            if not reading.name.matches and not reading.handle.matches:
                status = "both_fail"
            elif not reading.name.matches:
                status = "name_fail"
            else:
                status = "handle_fail"

        self.stats.ticks += 1
        result = CalibratedTickResult(
            tick=self._tick,
            elapsed_sec=time.time() - self.started_at,
            reading=reading,
            name_module=name_loc.module_label,
            handle_module=handle_loc.module_label,
            status=status,
            consecutive_ok=self._consecutive_ok,
            consecutive_fail=self._consecutive_fail,
        )
        self.history.append(result)
        return result

    def report_lines(self) -> list[str]:
        lines = [
            "=== 模式4 校准监控报告 ===",
            f"配置来源: {self.profile.source_mode}  创建于 {self.profile.created_at}",
            f"目标: {self.profile.expected_name} / {self.profile.expected_handle}",
            f"监控地址: 昵称 {self.profile.resolved_name_address():#x} "
            f"句柄 {self.profile.resolved_handle_address():#x}",
            f"采样: {self.stats.ticks} 次  成功率 {self.stats.success_rate():.0%} "
            f"(OK {self.stats.ok_ticks} / FAIL {self.stats.fail_ticks})",
        ]
        if self.stats.first_ok_at:
            lines.append(f"首次成功: {self.stats.first_ok_at - self.started_at:.1f}s 后")
        recent = self.history[-5:]
        if recent:
            lines.append("--- 最近采样 ---")
            for item in recent:
                lines.append(f"  {item.summary_line()}")
        return lines
