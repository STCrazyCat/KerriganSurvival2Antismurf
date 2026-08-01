"""Diagnose PaddleOCR lobby vision regions."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.config.settings import load_config
from antismurf.lobby.sc2_window import find_sc2_window
from antismurf.replay.local_replays import LocalReplayIndex
from antismurf.vision.handle_resolver import resolve_handle
from antismurf.vision.lobby_reader import LobbyReader
from antismurf.vision.lobby_text_parser import parse_lobby_identity
from antismurf.vision.screen_capture import capture_region, save_debug_image


def main() -> None:
    cfg = load_config()
    window = find_sc2_window(cfg.window_title_contains)
    if window is None:
        print("SC2 window not found")
        return

    print(f"Window: {window.width}x{window.height} at ({window.left}, {window.top})")
    replay_index = LocalReplayIndex(cfg)
    reader = LobbyReader(cfg, replay_index=replay_index)
    snapshot = reader.read_lobby_snapshot()

    if snapshot.error:
        print(f"Error: {snapshot.error}")

    print(f"Map OCR: {snapshot.map_ocr_text!r}")
    print(f"Map match: {snapshot.map_name!r}")
    print(f"Local host: {snapshot.is_local_host}")
    print(f"Players: {len(snapshot.handles)}")

    if cfg.map_region:
        image = capture_region(window, cfg.map_region)
        if image is not None:
            save_debug_image(image, "logs/vision/diagnose_map.png")
            print("Saved logs/vision/diagnose_map.png")

    for index, region in enumerate(cfg.slot_id_regions):
        image = capture_region(window, region)
        if image is None:
            continue
        path = f"logs/vision/diagnose_slot_{index}.png"
        save_debug_image(image, path)
        print(f"Saved {path}")

    for detail in snapshot.slot_details:
        print(
            f"  Slot {detail['index']}: ocr={detail.get('ocr_text')!r} "
            f"profile_id={detail.get('profile_id')} handle={detail.get('handle')}"
        )
        text = detail.get("ocr_text") or ""
        identity = parse_lobby_identity(text)
        if identity:
            handle = resolve_handle(identity, cfg, replay_index)
            print(f"    parsed handle via resolver: {handle}")


if __name__ == "__main__":
    main()
