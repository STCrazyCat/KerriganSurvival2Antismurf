"""Default lobby slot click regions derived from ``target/lobby_slots.png`` / full-screen capture."""

from __future__ import annotations

# KS2 lobby team-1 panel: 10 fixed slots, host usually in slot 1 (index 0).
# Measured on 1920x1080 client area from target/全屏截图.png (2026-07-06).
_SLOT_X = 0.124
_SLOT_Y_START = 0.321556
_SLOT_Y_STEP = 0.066588
LOBBY_UI_SLOT_COUNT = 10


def default_slot_regions() -> list[dict[str, float]]:
    return [
        {"x": _SLOT_X, "y": _SLOT_Y_START + index * _SLOT_Y_STEP}
        for index in range(LOBBY_UI_SLOT_COUNT)
    ]


def ui_slot_label(zero_based_index: int) -> str:
    """Display label for a lobby slot (1..10)."""
    return str(zero_based_index + 1)


def pad_slot_regions(
    regions: list[dict[str, float]],
    *,
    count: int = LOBBY_UI_SLOT_COUNT,
) -> list[dict[str, float]]:
    """Extend calibrated slot regions to ``count`` entries using last row spacing."""
    if len(regions) >= count:
        return regions[:count]
    if not regions:
        return default_slot_regions()
    if len(regions) == 1:
        out = list(regions)
        while len(out) < count:
            out.append(dict(out[-1]))
        return out
    dy = regions[-1]["y"] - regions[-2]["y"]
    dx = regions[-1]["x"]
    out = list(regions)
    while len(out) < count:
        out.append({"x": dx, "y": out[-1]["y"] + dy})
    return out
