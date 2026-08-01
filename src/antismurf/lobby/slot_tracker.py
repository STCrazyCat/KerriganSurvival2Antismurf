from __future__ import annotations

from antismurf.models.player import PlayerHandle


class SlotTracker:
    """Track lobby player handles across OCR polls."""

    def __init__(self) -> None:
        self._last_handles: dict[str, int] = {}

    def reset(self) -> None:
        self._last_handles.clear()

    def diff(
        self,
        slots: list[PlayerHandle],
    ) -> tuple[list[PlayerHandle], list[str]]:
        current = {player.handle: player for player in slots}
        joined = [
            player
            for handle, player in current.items()
            if handle not in self._last_handles
        ]
        left = [
            handle for handle in self._last_handles if handle not in current
        ]
        self._last_handles = {
            player.handle: player.slot_index for player in slots
        }
        return joined, left
