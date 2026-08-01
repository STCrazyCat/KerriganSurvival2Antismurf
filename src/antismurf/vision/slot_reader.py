from __future__ import annotations

import logging
from dataclasses import dataclass

from antismurf.config.settings import AppConfig
from antismurf.models.player import PlayerHandle
from antismurf.roster.store import PlayerRosterStore
from antismurf.vision.handle_resolver import local_profile_id
from antismurf.vision.handle_resolution import HandleResolution, resolve_handle_detailed
from antismurf.vision.lobby_text_parser import merge_ocr_lines, parse_lobby_identity
from antismurf.vision.ocr_engine import OcrEngine
from antismurf.vision.screen_capture import capture_region, save_debug_image

if True:
    from PIL import Image

    from antismurf.lobby.sc2_window import WindowRect

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SlotReadResult:
    slot_index: int
    ocr_text: str
    identity_raw: str | None
    profile_id: int | None
    handle: str | None
    display_name: str
    resolution: HandleResolution | None = None


def read_slot_identities(
    window: WindowRect,
    config: AppConfig,
    ocr: OcrEngine,
    *,
    roster_store: PlayerRosterStore | None = None,
    save_debug: bool = False,
) -> list[SlotReadResult]:
    results: list[SlotReadResult] = []
    regions = config.slot_id_regions or []
    local_pid = local_profile_id(config)

    for index, region in enumerate(regions):
        image = capture_region(window, region)
        if image is None:
            continue
        if save_debug:
            save_debug_image(image, f"logs/vision/slot_{index}.png")

        lines = ocr.recognize(image)
        ocr_text = merge_ocr_lines([line.text for line in lines])
        if not ocr_text:
            continue

        identity = parse_lobby_identity(ocr_text)
        if identity is None or identity.profile_id is None:
            results.append(
                SlotReadResult(
                    slot_index=index,
                    ocr_text=ocr_text,
                    identity_raw=ocr_text,
                    profile_id=None,
                    handle=None,
                    display_name=ocr_text,
                )
            )
            continue

        if local_pid is not None and identity.profile_id == local_pid:
            continue

        handle = resolve_handle_detailed(identity, config, roster_store)
        results.append(
            SlotReadResult(
                slot_index=index,
                ocr_text=ocr_text,
                identity_raw=identity.raw_text,
                profile_id=identity.profile_id,
                handle=handle.handle,
                display_name=identity.display_name,
                resolution=handle,
            )
        )
    return results


def slot_results_to_handles(
    results: list[SlotReadResult],
) -> list[PlayerHandle]:
    from antismurf.models.player import parse_handle_parts

    players: list[PlayerHandle] = []
    for item in results:
        if not item.handle:
            continue
        res = item.resolution
        extra = {
            "handle_ambiguous": res.ambiguous if res else False,
            "handle_candidate_count": res.candidate_count if res else 1,
            "handle_constructed": res.constructed if res else False,
            "ocr_digit_obfuscation": res.digit_obfuscation if res else False,
            "handle_from_binding": res.from_binding if res else False,
        }
        parts = parse_handle_parts(item.handle)
        if parts is not None and item.profile_id is not None:
            players.append(
                PlayerHandle.from_profile(
                    slot_index=item.slot_index,
                    region_id=parts.server_id,
                    realm_id=parts.realm_id,
                    profile_id=item.profile_id,
                    display_name=item.display_name,
                    **extra,
                )
            )
        else:
            players.append(
                PlayerHandle(
                    handle=item.handle,
                    slot_index=item.slot_index,
                    display_text=item.display_name or item.handle,
                    display_name=item.display_name,
                    **extra,
                )
            )
    return players
