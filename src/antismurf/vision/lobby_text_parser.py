from __future__ import annotations

import re
from dataclasses import dataclass

from antismurf.models.player import (
    extract_handle_from_text,
    is_valid_handle,
    parse_handle_parts,
)

# <#战队>#玩家ID  or  #玩家ID  or  玩家ID
LOBBY_ID_PATTERN = re.compile(
    r"(?:<#([^<>]{0,32})>)?#(\d{4,12})",
    re.IGNORECASE,
)
DIGITS_ONLY = re.compile(r"^\d{4,12}$")
# Letters often confused with digits in SC2 lobby OCR (1/l/I, 0/O)
OCR_AMBIGUOUS_ID_CHARS = re.compile(r"[lLoOiI]")


@dataclass(frozen=True)
class LobbyIdentity:
    raw_text: str
    display_name: str
    profile_id: int | None
    team: str | None = None
    handle: str | None = None
    digit_obfuscation: bool = False


def normalize_ocr_text(text: str) -> str:
    text = text.strip()
    text = text.replace("＃", "#").replace("＜", "<").replace("＞", ">")
    text = re.sub(r"\s+", "", text)
    return text


def digit_obfuscation_suspected(text: str) -> bool:
    """Detect 1/l/I or 0/O style obfuscation in lobby player ID OCR."""
    raw = text.strip()
    if not raw:
        return False
    if OCR_AMBIGUOUS_ID_CHARS.search(raw):
        return True
    normalized = normalize_ocr_text(raw)
    if OCR_AMBIGUOUS_ID_CHARS.search(normalized):
        return True
    if re.search(r"[A-Za-z]", normalized):
        id_match = LOBBY_ID_PATTERN.search(normalized)
        if id_match and OCR_AMBIGUOUS_ID_CHARS.search(id_match.group(2)):
            return True
        if DIGITS_ONLY.match(re.sub(r"[lLoOiI]", "", normalized)):
            return True
    return False


def _normalize_digit_obfuscation(text: str) -> str:
    """Best-effort correction for common OCR digit mistakes."""
    out: list[str] = []
    for ch in text:
        if ch in ("l", "L", "I", "|"):
            out.append("1")
        elif ch in ("o", "O"):
            out.append("0")
        else:
            out.append(ch)
    return "".join(out)


def parse_lobby_identity(text: str) -> LobbyIdentity | None:
    """Parse OCR text into lobby player identity."""
    raw = text.strip()
    if not raw:
        return None

    obfuscation = digit_obfuscation_suspected(raw)
    normalized = normalize_ocr_text(raw)
    if obfuscation:
        normalized = _normalize_digit_obfuscation(normalized)

    handle = extract_handle_from_text(normalized)
    if handle and is_valid_handle(handle):
        parts = parse_handle_parts(handle)
        return LobbyIdentity(
            raw_text=raw,
            display_name=raw,
            profile_id=parts.player_id if parts else None,
            handle=handle,
            digit_obfuscation=obfuscation,
        )

    match = LOBBY_ID_PATTERN.search(normalized)
    if not match and obfuscation:
        corrected = _normalize_digit_obfuscation(normalize_ocr_text(raw))
        match = LOBBY_ID_PATTERN.search(corrected)
        if not match and DIGITS_ONLY.match(corrected):
            profile_id = int(corrected)
            return LobbyIdentity(
                raw_text=raw,
                display_name=raw,
                profile_id=profile_id,
                digit_obfuscation=True,
            )

    if match:
        team = (match.group(1) or "").strip() or None
        profile_id = int(match.group(2))
        display = raw
        if team:
            display = f"<#{team}>#{profile_id}"
        elif not raw.startswith("#") and not raw.startswith("<"):
            display = f"#{profile_id}"
        return LobbyIdentity(
            raw_text=raw,
            display_name=display,
            profile_id=profile_id,
            team=team,
            digit_obfuscation=obfuscation,
        )

    if DIGITS_ONLY.match(normalized):
        profile_id = int(normalized)
        return LobbyIdentity(
            raw_text=raw,
            display_name=normalized,
            profile_id=profile_id,
            digit_obfuscation=obfuscation,
        )

    if obfuscation:
        corrected = _normalize_digit_obfuscation(normalized)
        if DIGITS_ONLY.match(corrected):
            return LobbyIdentity(
                raw_text=raw,
                display_name=raw,
                profile_id=int(corrected),
                digit_obfuscation=True,
            )

    return None


def merge_ocr_lines(lines: list[str]) -> str:
    return "".join(line.strip() for line in lines if line.strip())
