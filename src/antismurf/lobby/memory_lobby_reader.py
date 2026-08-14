from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from antismurf.config.settings import AppConfig, _project_root
from antismurf.lobby.memory_lobby_auto_confirm import (
    LobbyAutoConfirmSession,
    LobbyAutoConfirmSnapshot,
)
from antismurf.lobby.probe_calibration import CalibratedProfile, load_profile
from antismurf.lobby.sc2_process import (
    close_process,
    list_sc2_pids,
    open_process_for_read,
    resolve_sc2_pid,
)
from antismurf.models.player import PlayerHandle, parse_handle_parts
from antismurf.vision.lobby_reader import LobbySnapshot

logger = logging.getLogger(__name__)


@dataclass
class RosterScanState:
    record_base: int | None = None
    record_base_source: str = "none"
    phase: str = "unknown"
    in_room: bool = False
    room_created: bool = False
    member_count: int = 0
    scan_count: int = 0
    handle_location_state: str = "unknown"  # confirmed / unconfirmed
    handle_location_source: str = "none"    # anchor / sniff / accounts / roster
    host_handle_address: int | None = None
    roster_verified: bool = False


class MemoryLobbyReader:
    """Read KS2 lobby players via Mode 6 (LobbyAutoConfirmSession)."""

    def __init__(
        self,
        config: AppConfig,
        *,
        calibration: CalibratedProfile | None = None,
    ) -> None:
        self._config = config
        self._last_pid: int | None = None
        self._cached_local_handle: str | None = None
        self._roster_state = RosterScanState()
        self._process_handle = None
        self._auto_confirm: LobbyAutoConfirmSession | None = None
        self._lobby_active_fast = False
        self._calibration = calibration
        if self._calibration is None:
            cal_path = Path(config.memory_calibration_path)
            if not cal_path.is_absolute():
                cal_path = _project_root() / cal_path
            self._calibration = load_profile(cal_path)

    @property
    def roster_state(self) -> RosterScanState:
        return self._roster_state

    def reset_session(self) -> None:
        self._last_pid = None
        self._cached_local_handle = None
        self._roster_state = RosterScanState()
        self._auto_confirm = None
        self._lobby_active_fast = False
        self._close_process()

    def set_lobby_active(self, active: bool) -> None:
        """Switch roster rescan cadence: fast memory reads in-room, rare rescans."""
        self._lobby_active_fast = active
        if self._auto_confirm is not None:
            every = (
                self._config.memory_roster_rescan_every_scans_in_room
                if active
                else self._config.memory_roster_rescan_every_scans
            )
            self._auto_confirm.set_rescan_every_ticks(every)

    def _close_process(self) -> None:
        if self._process_handle is not None:
            close_process(self._process_handle)
            self._process_handle = None

    def read_lobby_snapshot(
        self,
        force_reconfirm: bool = False,
    ) -> LobbySnapshot:
        if not self._config.memory_enabled:
            return LobbySnapshot(
                None,
                None,
                None,
                None,
                error="Memory scan disabled",
            )

        pids = list_sc2_pids(self._config.memory_process_names)
        if not pids:
            return LobbySnapshot(
                None,
                None,
                None,
                None,
                error="SC2 进程未运行 (SC2_x64.exe)",
            )

        pid = resolve_sc2_pid(
            process_names=self._config.memory_process_names,
            target_pid=self._config.memory_target_pid or None,
            title_hints=(
                self._config.window_title_contains,
                "StarCraft",
                "星际争霸",
                "星海争霸",
            ),
        )
        if pid is None:
            return LobbySnapshot(
                None,
                None,
                None,
                None,
                window_found=True,
                error="无法解析 SC2 进程（请在界面中选择 PID）",
            )

        if pid != self._last_pid:
            self.reset_session()
            self._last_pid = pid

        try:
            session = self._ensure_mode6_session(pid)
        except OSError as exc:
            return LobbySnapshot(
                None,
                None,
                None,
                None,
                window_found=True,
                error=str(exc),
            )

        snap = session.tick(force_rescan=force_reconfirm)
        self._roster_state.scan_count = snap.tick
        self._roster_state.phase = snap.phase.value
        self._roster_state.in_room = snap.in_room
        self._roster_state.room_created = snap.room_created
        self._roster_state.member_count = snap.member_count
        self._roster_state.record_base = snap.record_base
        self._roster_state.record_base_source = snap.record_base_source
        self._roster_state.handle_location_state = snap.handle_location_state
        self._roster_state.handle_location_source = snap.handle_location_source
        self._roster_state.host_handle_address = snap.host_handle_address
        self._roster_state.roster_verified = snap.roster_verified

        if snap.host_handle in {"", "?"}:
            return LobbySnapshot(
                None,
                None,
                None,
                None,
                window_found=True,
                error="无法读取主机句柄 (SC2+3E2F340)，请确认 SC2 已启动",
            )

        if not snap.host_anchor_ok:
            logger.warning(
                "Using fallback host handle %s (module anchor unreadable)",
                snap.host_handle,
            )

        self._cached_local_handle = snap.host_handle

        if not snap.in_room:
            return LobbySnapshot(
                map_name=None,
                map_ocr_text=None,
                host_handle=snap.host_handle,
                local_handle=snap.host_handle,
                is_local_host=False,
                handles=[],
                slot_details=[],
                window_found=True,
                error=None,
            )

        return self._mode6_snapshot_to_lobby(snap)

    def _ensure_mode6_session(self, pid: int) -> LobbyAutoConfirmSession:
        if self._auto_confirm is not None and self._process_handle is not None:
            return self._auto_confirm

        self._process_handle = open_process_for_read(pid)
        host_offset = self._config.memory_host_handle_module_offset
        if (
            self._calibration
            and self._calibration.host_handle_module_offset is not None
        ):
            host_offset = self._calibration.host_handle_module_offset
        self._auto_confirm = LobbyAutoConfirmSession(
            self._process_handle,
            pid=pid,
            host_handle_module_offset=host_offset,
            calibration=self._calibration,
            rescan_budget_sec=self._config.memory_roster_rescan_budget_sec,
            rescan_every_ticks=max(1, self._config.memory_roster_rescan_every_scans),
            fallback_host_handle=self._config.host_handle,
            sniff_enabled=self._config.memory_host_anchor_sniff_enabled,
            sniff_radius=self._config.memory_host_anchor_scan_radius,
            calibration_path=self._config.memory_calibration_path,
        )
        return self._auto_confirm

    def _mode6_snapshot_to_lobby(self, snap: LobbyAutoConfirmSnapshot) -> LobbySnapshot:
        local_handle = snap.host_handle
        players: list[PlayerHandle] = []
        slot_details: list[dict] = []

        for member in snap.members:
            handle = member.handle
            display_name = member.display_name if member.display_name != "?" else ""
            team_name = member.team_name or ""
            from_binding = False

            parts = parse_handle_parts(handle)
            if parts is None:
                continue
            players.append(
                PlayerHandle.from_profile(
                    slot_index=member.slot,
                    region_id=parts.server_id,
                    realm_id=parts.realm_id,
                    profile_id=parts.player_id,
                    display_name=display_name,
                    team_name=team_name,
                    handle_from_binding=from_binding,
                    handle_candidate_count=1,
                )
            )
            slot_details.append(
                {
                    "index": member.slot,
                    "ocr_text": display_name,
                    "profile_id": parts.player_id,
                    "handle": handle,
                    "display_name": display_name,
                    "team_name": team_name,
                    "raw_display_name": member.raw_display_name or display_name,
                    "source": "memory_roster",
                    "name_source": (
                        "roster_struct"
                        if member.display_name and member.display_name != "?"
                        else ("replay_db" if from_binding else "none")
                    ),
                    "record_base": member.record_base,
                    "profile_address": member.profile_address,
                }
            )

        map_name = self._config.target_maps[0] if self._config.target_maps else "凯瑞甘生存2"
        is_local_host = bool(
            local_handle
            and (
                snap.room_created
                or any(item.is_host for item in snap.members)
            )
        )

        logger.debug(
            "Mode6 roster: base=%#x source=%s members=%s room_created=%s",
            snap.record_base or 0,
            snap.record_base_source,
            len(snap.members),
            snap.room_created,
        )

        return LobbySnapshot(
            map_name=map_name,
            map_ocr_text=map_name,
            host_handle=local_handle if is_local_host else None,
            local_handle=local_handle,
            is_local_host=is_local_host,
            handles=players,
            slot_details=slot_details,
            window_found=True,
            error=None,
        )

    def preview(self) -> dict:
        snapshot = self.read_lobby_snapshot()
        roster = self._roster_state
        return {
            "mode": "memory_mode6",
            "scan_mode": "roster",
            "enabled": self._config.memory_enabled,
            "pid": self._last_pid,
            "roster_base": roster.record_base,
            "roster_base_source": roster.record_base_source,
            "roster_phase": roster.phase,
            "roster_in_room": roster.in_room,
            "roster_room_created": roster.room_created,
            "roster_member_count": roster.member_count,
            "handle_location_state": roster.handle_location_state,
            "handle_location_source": roster.handle_location_source,
            "host_handle_address": roster.host_handle_address,
            "roster_verified": roster.roster_verified,
            "calibration_loaded": self._calibration is not None,
            "window_found": snapshot.window_found,
            "in_ks2_lobby": roster.in_room and bool(snapshot.handles),
            "map_name": snapshot.map_name,
            "slots": snapshot.slot_details,
            "local_handle": snapshot.local_handle,
            "is_local_host": snapshot.is_local_host,
            "error": snapshot.error,
        }
