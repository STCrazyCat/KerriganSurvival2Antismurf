from __future__ import annotations

import logging

from antismurf.config.settings import AppConfig
from antismurf.vision.map_detector import is_target_map

logger = logging.getLogger(__name__)


class MapGuard:
    """Track KS2 lobby presence from OCR map detection."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._active = False
        self._last_map_name: str | None = None
        self._empty_ticks = 0
        self._exit_grace_ticks = 3
        self._manual_lock = False

    @property
    def manual_lock(self) -> bool:
        return self._manual_lock

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def last_map_name(self) -> str | None:
        return self._last_map_name

    def update(
        self,
        map_name: str | None,
        *,
        lobby_player_count: int = 0,
    ) -> str | None:
        """Return 'enter', 'exit', or None on state transition."""
        if self._manual_lock:
            return None

        matched = is_target_map(map_name, self._config.target_maps)
        player_ok = 0 < lobby_player_count <= 8

        if matched and player_ok:
            self._empty_ticks = 0
            if not self._active:
                self._active = True
                self._last_map_name = map_name
                logger.info(
                    "Entered KS2 lobby by OCR (%s players, map=%s)",
                    lobby_player_count,
                    map_name or "unknown",
                )
                return "enter"
            self._last_map_name = map_name
            return None

        if matched and not player_ok:
            self._empty_ticks = 0
            if self._active:
                return None
            return None

        if self._active:
            self._empty_ticks += 1
            if self._empty_ticks >= self._exit_grace_ticks:
                self._active = False
                self._last_map_name = None
                self._empty_ticks = 0
                logger.info("Left KS2 lobby (OCR map mismatch or empty)")
                return "exit"
        return None

    def force_active(self, map_name: str | None, *, manual: bool = False) -> None:
        self._active = True
        self._last_map_name = map_name
        self._empty_ticks = 0
        self._manual_lock = manual

    def release_manual(self) -> None:
        self._manual_lock = False

    def reset(self) -> None:
        self._active = False
        self._last_map_name = None
        self._empty_ticks = 0
        self._manual_lock = False
