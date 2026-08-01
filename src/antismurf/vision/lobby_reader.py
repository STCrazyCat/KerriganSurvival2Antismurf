from __future__ import annotations

import logging
from dataclasses import dataclass, field

from antismurf.config.settings import AppConfig
from antismurf.lobby.sc2_window import find_sc2_window
from antismurf.models.player import PlayerHandle, parse_handle_parts
from antismurf.roster.store import PlayerRosterStore
from antismurf.vision.handle_resolver import local_profile_id
from antismurf.vision.map_detector import best_map_match, is_target_map
from antismurf.vision.ocr_engine import OcrEngine, create_ocr_engine
from antismurf.vision.screen_capture import capture_region, save_debug_image
from antismurf.vision.slot_reader import (
    read_slot_identities,
    slot_results_to_handles,
)
from antismurf.vision.lobby_text_parser import merge_ocr_lines

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LobbySnapshot:
    map_name: str | None
    map_ocr_text: str | None
    host_handle: str | None
    local_handle: str | None
    is_local_host: bool = False
    handles: list[PlayerHandle] = field(default_factory=list)
    slot_details: list[dict] = field(default_factory=list)
    window_found: bool = False
    error: str | None = None


class LobbyReader:
    """Read KS2 lobby state via screen OCR."""

    def __init__(
        self,
        config: AppConfig,
        *,
        roster_store: PlayerRosterStore | None = None,
        ocr: OcrEngine | None = None,
    ) -> None:
        self._config = config
        self._roster_store = roster_store
        self._ocr = ocr

    def _get_ocr(self) -> OcrEngine:
        if self._ocr is None:
            self._ocr = create_ocr_engine(
                self._config.vision_engine,
                use_gpu=self._config.vision_use_gpu,
                min_confidence=self._config.vision_min_confidence,
            )
        return self._ocr

    def read_lobby_snapshot(self) -> LobbySnapshot:
        if not self._config.vision_enabled:
            return LobbySnapshot(
                None,
                None,
                None,
                self._config.host_handle or None,
                error="Vision OCR disabled",
            )

        window = find_sc2_window(self._config.window_title_contains)
        if window is None:
            return LobbySnapshot(
                None,
                None,
                None,
                self._config.host_handle or None,
                error="SC2 window not found",
            )

        ocr = self._get_ocr()
        map_region = self._config.map_region
        map_ocr_text: str | None = None
        map_name: str | None = None

        if map_region:
            map_image = capture_region(window, map_region)
            if map_image is not None:
                if self._config.vision_save_debug_images:
                    save_debug_image(map_image, "logs/vision/map.png")
                map_lines = ocr.recognize(map_image)
                map_ocr_text = merge_ocr_lines([line.text for line in map_lines])
                map_name = best_map_match(map_ocr_text, self._config.target_maps)

        slot_results = read_slot_identities(
            window,
            self._config,
            ocr,
            roster_store=self._roster_store,
            save_debug=self._config.vision_save_debug_images,
        )
        handles = slot_results_to_handles(slot_results)

        local_handle = (self._config.host_handle or "").strip() or None
        local_pid = local_profile_id(self._config)
        is_local_host = False
        if local_pid is not None and slot_results:
            slot0 = next((s for s in slot_results if s.slot_index == 0), None)
            if slot0 and slot0.profile_id == local_pid:
                is_local_host = True
        elif local_handle:
            parts = parse_handle_parts(local_handle)
            if parts and slot_results:
                slot0 = next((s for s in slot_results if s.slot_index == 0), None)
                if slot0 and slot0.profile_id == parts.player_id:
                    is_local_host = True

        slot_details = [
            {
                "index": item.slot_index,
                "ocr_text": item.ocr_text,
                "profile_id": item.profile_id,
                "handle": item.handle,
                "display_name": item.display_name,
            }
            for item in slot_results
        ]

        return LobbySnapshot(
            map_name=map_name,
            map_ocr_text=map_ocr_text,
            host_handle=local_handle if is_local_host else None,
            local_handle=local_handle,
            is_local_host=is_local_host,
            handles=handles,
            slot_details=slot_details,
            window_found=True,
        )

    def preview(self) -> dict:
        snapshot = self.read_lobby_snapshot()
        return {
            "window_found": snapshot.window_found,
            "in_ks2_lobby": is_target_map(snapshot.map_name, self._config.target_maps),
            "map_name": snapshot.map_name,
            "map_ocr_text": snapshot.map_ocr_text,
            "map_active": is_target_map(snapshot.map_name, self._config.target_maps),
            "slots": [
                {
                    "index": item["index"],
                    "handle": item.get("handle") or "",
                    "display_name": item.get("display_name") or "",
                    "profile_id": item.get("profile_id"),
                    "ocr_text": item.get("ocr_text") or "",
                    "text": item.get("ocr_text") or item.get("display_name") or "",
                }
                for item in snapshot.slot_details
            ],
            "local_handle": snapshot.local_handle,
            "is_local_host": snapshot.is_local_host,
            "error": snapshot.error,
        }
