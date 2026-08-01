from __future__ import annotations

import re


def normalize_map_text(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"\s+", "", text)
    return text


def is_target_map(map_name: str | None, target_maps: list[str]) -> bool:
    if not map_name:
        return False
    normalized = normalize_map_text(map_name)
    if not normalized:
        return False
    for target in target_maps:
        target_norm = normalize_map_text(target)
        if not target_norm:
            continue
        if target_norm in normalized or normalized in target_norm:
            return True
    return False


def best_map_match(
    ocr_text: str,
    target_maps: list[str],
) -> str | None:
    """Return the first target map name that matches OCR text."""
    if not ocr_text.strip():
        return None
    normalized = normalize_map_text(ocr_text)
    for target in target_maps:
        target_norm = normalize_map_text(target)
        if target_norm and target_norm in normalized:
            return target
    for target in target_maps:
        target_norm = normalize_map_text(target)
        if target_norm and normalized in target_norm:
            return target
    return None
