from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image

    from antismurf.lobby.sc2_window import WindowRect


def region_to_pixels(
    window: WindowRect,
    region: dict[str, float],
) -> tuple[int, int, int, int]:
    """Convert relative region to absolute left, top, width, height."""
    x = max(0.0, min(1.0, float(region.get("x", 0.0))))
    y = max(0.0, min(1.0, float(region.get("y", 0.0))))
    w = max(0.01, min(1.0 - x, float(region.get("w", 0.02))))
    h = max(0.01, min(1.0 - y, float(region.get("h", 0.02))))
    left = int(window.left + window.width * x)
    top = int(window.top + window.height * y)
    width = max(1, int(window.width * w))
    height = max(1, int(window.height * h))
    return left, top, width, height


def capture_region(
    window: WindowRect,
    region: dict[str, float],
) -> Image.Image | None:
    """Capture a relative region inside the SC2 window."""
    try:
        import mss
        from PIL import Image
    except ImportError:
        return None

    left, top, width, height = region_to_pixels(window, region)
    monitor = {"left": left, "top": top, "width": width, "height": height}
    with mss.mss() as sct:
        shot = sct.grab(monitor)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


def save_debug_image(image: Image.Image, path) -> None:
    from pathlib import Path

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target)
