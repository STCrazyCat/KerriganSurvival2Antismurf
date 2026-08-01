from __future__ import annotations



import logging

import time

from pathlib import Path



from antismurf.actions.kick_script import kick_player_slot

from antismurf.config.kick_defaults import LOBBY_UI_SLOT_COUNT, ui_slot_label

from antismurf.config.settings import AppConfig

from antismurf.lobby.sc2_window import activate_sc2_window, find_sc2_window, is_sc2_foreground



logger = logging.getLogger(__name__)





class Kicker:

    def __init__(self, config: AppConfig) -> None:

        self._config = config

        self._last_kick_at = 0.0



    def kick_slot(self, slot_index: int) -> bool:

        if slot_index < 0 or slot_index >= LOBBY_UI_SLOT_COUNT:

            logger.error(

                "Invalid slot index %s (UI slots are 1..%s)",

                slot_index,

                LOBBY_UI_SLOT_COUNT,

            )

            return False



        ui_slot = ui_slot_label(slot_index)

        if self._config.dry_run:

            logger.info("[dry_run] Would kick UI slot %s (index %s)", ui_slot, slot_index)

            return True



        now = time.time()

        if now - self._last_kick_at < self._config.kick_cooldown_sec:

            logger.warning("Kick cooldown active")

            return False



        title = self._config.window_title_contains

        if not activate_sc2_window(title, wait_sec=self._config.kick_focus_wait_sec):

            logger.error("Could not focus SC2 window before kicking slot %s", ui_slot)

            return False

        if not is_sc2_foreground(title):

            logger.error("SC2 is not foreground after activation (slot %s)", ui_slot)

            return False



        window = find_sc2_window(title)

        if window is None:

            logger.error("SC2 client rect lost before kick slot %s", ui_slot)

            return False



        ok = kick_player_slot(self._config, slot_index, window=window)

        if ok:

            self._last_kick_at = now

            self._save_debug_shot(slot_index, success=True)

        else:

            self._save_debug_shot(slot_index, success=False)

        return ok



    def _save_debug_shot(self, slot_index: int, success: bool) -> None:

        if not self._config.kick_save_debug_shots:

            return

        try:

            import mss

            from PIL import Image



            log_dir = Path("logs/kick_failures")

            log_dir.mkdir(parents=True, exist_ok=True)

            tag = "ok" if success else "fail"

            path = log_dir / f"slot{ui_slot_label(slot_index)}_{tag}_{int(time.time())}.png"

            with mss.mss() as sct:

                shot = sct.grab(sct.monitors[0])

                Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX").save(path)

        except Exception:

            pass


