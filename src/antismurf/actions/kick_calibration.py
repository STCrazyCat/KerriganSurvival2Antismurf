"""Kick coordinate calibration: fixed slot/menu offsets and dry-run OCR detection."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from antismurf.config.kick_defaults import LOBBY_UI_SLOT_COUNT, default_slot_regions
from antismurf.config.settings import AppConfig
from antismurf.lobby.sc2_window import WindowRect, activate_sc2_window, find_sc2_window

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KickCalibrationResult:
    ok: bool
    message: str
    slot_index: int | None = None
    slot_click: dict[str, float] | None = None
    menu_click: dict[str, float] | None = None
    menu_offset: dict[str, float] | None = None
    slot_step: dict[str, float] | None = None
    template_score: float | None = None


def normalized_offset(
    from_xy: tuple[float, float],
    to_xy: tuple[float, float],
) -> dict[str, float]:
    return {"dx": to_xy[0] - from_xy[0], "dy": to_xy[1] - from_xy[1]}


def derive_slot_regions(
    anchor: dict[str, float],
    step: dict[str, float],
    *,
    count: int = LOBBY_UI_SLOT_COUNT,
) -> list[dict[str, float]]:
    regions: list[dict[str, float]] = []
    dx = float(step.get("dx", 0.0))
    dy = float(step.get("dy", 0.0))
    base_x = float(anchor["x"])
    base_y = float(anchor["y"])
    for index in range(count):
        regions.append({"x": base_x + dx * index, "y": base_y + dy * index})
    return regions


def apply_manual_menu_offset(
    slot_click: dict[str, float],
    menu_click: dict[str, float],
) -> KickCalibrationResult:
    """Record menu offset relative to a slot right-click anchor."""
    if "x" not in slot_click or "y" not in slot_click:
        return KickCalibrationResult(False, "缺少槽位右键坐标")
    if "x" not in menu_click or "y" not in menu_click:
        return KickCalibrationResult(False, "缺少菜单点击坐标")

    offset = normalized_offset(
        (float(slot_click["x"]), float(slot_click["y"])),
        (float(menu_click["x"]), float(menu_click["y"])),
    )
    return KickCalibrationResult(
        ok=True,
        message=(
            f"菜单偏移 dx={offset['dx']:.4f} dy={offset['dy']:.4f} "
            f"（相对 1 号槽基准）"
        ),
        slot_index=0,
        slot_click=dict(slot_click),
        menu_click=dict(menu_click),
        menu_offset=offset,
    )


def apply_slot_step_from_two_anchors(
    slot1_click: dict[str, float],
    slot2_click: dict[str, float],
) -> KickCalibrationResult:
    """Derive vertical slot spacing from manually marked slot 1 and 2."""
    step = normalized_offset(
        (float(slot1_click["x"]), float(slot1_click["y"])),
        (float(slot2_click["x"]), float(slot2_click["y"])),
    )
    slots = derive_slot_regions(slot1_click, step)
    return KickCalibrationResult(
        ok=True,
        message=f"槽位步进 dx={step['dx']:.4f} dy={step['dy']:.4f}，已推导 10 槽",
        slot_click=dict(slot1_click),
        slot_step=step,
    )


def apply_spectator_calibration(
    slot_click: dict[str, float],
    spectator_click: dict[str, float],
    *,
    slot_step: dict[str, float] | None = None,
) -> KickCalibrationResult:
    """Map self right-click +「设为观战者」to slot grid and menu offset.

    The spectator item shares the same menu row as「移出房间」when right-clicking others.
    """
    if "x" not in slot_click or "y" not in slot_click:
        return KickCalibrationResult(False, "缺少 1 号槽右键坐标")
    if "x" not in spectator_click or "y" not in spectator_click:
        return KickCalibrationResult(False, "缺少观战者菜单坐标")

    offset = normalized_offset(
        (float(slot_click["x"]), float(slot_click["y"])),
        (float(spectator_click["x"]), float(spectator_click["y"])),
    )
    step = slot_step or {"dx": 0.0, "dy": default_slot_regions()[1]["y"] - default_slot_regions()[0]["y"]}
    slots = derive_slot_regions(slot_click, step)
    return KickCalibrationResult(
        ok=True,
        message=(
            f"已生成 {len(slots)} 槽；菜单偏移 dx={offset['dx']:.4f} dy={offset['dy']:.4f}"
        ),
        slot_index=0,
        slot_click=dict(slot_click),
        menu_click=dict(spectator_click),
        menu_offset=offset,
        slot_step=step,
    )


def apply_two_slot_calibration(
    slot1_click: dict[str, float],
    slot2_click: dict[str, float],
    menu_click: dict[str, float],
) -> KickCalibrationResult:
    """Derive slot step from two slot right-clicks plus shared menu action point."""
    step = normalized_offset(
        (float(slot1_click["x"]), float(slot1_click["y"])),
        (float(slot2_click["x"]), float(slot2_click["y"])),
    )
    offset = normalized_offset(
        (float(slot2_click["x"]), float(slot2_click["y"])),
        (float(menu_click["x"]), float(menu_click["y"])),
    )
    slots = derive_slot_regions(slot1_click, step)
    return KickCalibrationResult(
        ok=True,
        message=(
            f"双槽校准：步进 dy={step['dy']:.4f}，菜单偏移 dy={offset['dy']:.4f}"
        ),
        slot_index=1,
        slot_click=dict(slot2_click),
        menu_click=dict(menu_click),
        menu_offset=offset,
        slot_step=step,
    )


def menu_click_from_slot(
    slot_region: dict[str, float],
    menu_offset: dict[str, float],
) -> dict[str, float]:
    return {
        "x": float(slot_region["x"]) + float(menu_offset.get("dx", 0.0)),
        "y": float(slot_region["y"]) + float(menu_offset.get("dy", 0.0)),
    }


def dry_run_kick_calibration(
    config: AppConfig,
    slot_index: int = 1,
) -> KickCalibrationResult:
    """Right-click target slot, OCR-detect「移出房间」position, do not confirm kick."""
    from antismurf.actions.menu_locator import detect_kick_menu_remove_region

    if slot_index < 0 or slot_index >= LOBBY_UI_SLOT_COUNT:
        return KickCalibrationResult(False, f"槽位索引无效: {slot_index}")

    title = config.window_title_contains
    if not activate_sc2_window(title, wait_sec=config.kick_focus_wait_sec):
        return KickCalibrationResult(False, "无法聚焦 SC2 窗口")

    window = find_sc2_window(title)
    if window is None:
        return KickCalibrationResult(False, "未找到 SC2 客户区")

    region = _slot_region(config, slot_index)
    if region is None:
        return KickCalibrationResult(False, f"槽位 {slot_index + 1} 未校准")

    x = int(window.left + window.width * region["x"])
    y = int(window.top + window.height * region["y"])

    try:
        import pyautogui

        pyautogui.click(x, y, button="right")
        time.sleep(max(0.25, config.kick_menu_open_wait_sec))
        detected = detect_kick_menu_remove_region(
            title,
            config.kick_menu_template_path,
            anchor_xy=(x, y),
        )
        pyautogui.press("esc")
        time.sleep(0.05)
    except Exception as exc:
        return KickCalibrationResult(False, f"模拟踢人失败: {exc}")

    if not detected:
        return KickCalibrationResult(
            False,
            f"槽位 {slot_index + 1} OCR 未识别到踢人菜单（请确认该槽有玩家且菜单已打开）",
            slot_index=slot_index,
            slot_click=dict(region),
        )

    offset = normalized_offset((region["x"], region["y"]), (detected["x"], detected["y"]))
    return KickCalibrationResult(
        ok=True,
        message=(
            f"槽位 {slot_index + 1} OCR 检测到移出菜单 "
            f"({detected['x']:.4f}, {detected['y']:.4f})，偏移 dy={offset['dy']:.4f}"
        ),
        slot_index=slot_index,
        slot_click=dict(region),
        menu_click=detected,
        menu_offset=offset,
    )


def apply_calibration_result(config: AppConfig, result: KickCalibrationResult) -> None:
    if not result.ok:
        return
    if result.menu_offset:
        config.kick_menu_offset = dict(result.menu_offset)
    if result.slot_step:
        config.kick_slot_step = dict(result.slot_step)
    if result.menu_click:
        config.kick_menu_remove_region = dict(result.menu_click)
    if result.slot_step and result.slot_click and result.slot_index in (0, None):
        config.slot_regions = derive_slot_regions(result.slot_click, result.slot_step)
    elif result.slot_click and result.slot_index == 0 and not config.slot_regions:
        step = config.kick_slot_step or {"dx": 0.0, "dy": 0.066588}
        config.slot_regions = derive_slot_regions(result.slot_click, step)
    elif (
        config.slot_regions
        and config.kick_slot_step
        and len(config.slot_regions) < LOBBY_UI_SLOT_COUNT
    ):
        config.slot_regions = derive_slot_regions(
            config.slot_regions[0], config.kick_slot_step
        )


def _slot_region(config: AppConfig, slot_index: int) -> dict[str, float] | None:
    if slot_index < len(config.slot_regions):
        return config.slot_regions[slot_index]
    if config.slot_regions and config.kick_slot_step:
        derived = derive_slot_regions(config.slot_regions[0], config.kick_slot_step)
        if slot_index < len(derived):
            return derived[slot_index]
    return None
