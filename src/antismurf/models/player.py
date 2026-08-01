from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# Format: {server}-S2-{realm}-{player_id}  e.g. 5-S2-1-1234567
HANDLE_PATTERN = re.compile(r"^(\d+)-S2-(\d+)-(\d+)$")
HANDLE_SEARCH_PATTERN = re.compile(r"\d+-S2-\d+-\d+")
HANDLE_ASCII_BYTES = re.compile(rb"\d+-S2-\d+-\d+")

SuspicionTier = Literal["low", "medium", "high", "critical"]


@dataclass(frozen=True)
class HandleParts:
    server_id: int
    realm_id: int
    player_id: int

    @property
    def full(self) -> str:
        return f"{self.server_id}-S2-{self.realm_id}-{self.player_id}"


def parse_handle_parts(text: str) -> HandleParts | None:
    text = text.strip()
    match = HANDLE_PATTERN.match(text)
    if not match:
        return None
    return HandleParts(
        server_id=int(match.group(1)),
        realm_id=int(match.group(2)),
        player_id=int(match.group(3)),
    )


def parse_handle(text: str) -> tuple[str, int | None]:
    """Parse handle into (full_handle, player_id)."""
    parts = parse_handle_parts(text)
    if parts is None:
        return text.strip(), None
    return parts.full, parts.player_id


def is_valid_handle(text: str) -> bool:
    return parse_handle_parts(text.strip()) is not None


def extract_handle_from_text(text: str) -> str | None:
    """Find the first KS2 handle in arbitrary replay/UI text."""
    text = text.strip()
    if is_valid_handle(text):
        return text
    match = HANDLE_SEARCH_PATTERN.search(text)
    if match and is_valid_handle(match.group(0)):
        return match.group(0)
    return None


class PlayerHandle(BaseModel):
    handle: str
    slot_index: int
    display_text: str = ""
    display_name: str = ""
    team_name: str = ""
    discriminator: int | None = None
    profile_id: int | None = None
    profile_ref: str = ""
    server_id: int | None = None
    realm_id: int | None = None
    first_seen_at: datetime = Field(default_factory=datetime.now)
    handle_ambiguous: bool = False
    handle_candidate_count: int = 1
    handle_constructed: bool = False
    ocr_digit_obfuscation: bool = False
    handle_from_binding: bool = False

    @classmethod
    def from_profile(
        cls,
        *,
        slot_index: int,
        region_id: int,
        realm_id: int,
        profile_id: int,
        display_name: str = "",
        team_name: str = "",
        handle_ambiguous: bool = False,
        handle_candidate_count: int = 1,
        handle_constructed: bool = False,
        ocr_digit_obfuscation: bool = False,
        handle_from_binding: bool = False,
    ) -> PlayerHandle:
        handle = f"{region_id}-S2-{realm_id}-{profile_id}"
        profile_ref = f"{region_id}/{realm_id}/{profile_id}"
        label = display_name or handle
        return cls(
            handle=handle,
            slot_index=slot_index,
            display_name=display_name,
            team_name=team_name,
            display_text=f"{label}  ({handle})" if display_name else handle,
            discriminator=profile_id,
            profile_id=profile_id,
            profile_ref=profile_ref,
            server_id=region_id,
            realm_id=realm_id,
            handle_ambiguous=handle_ambiguous,
            handle_candidate_count=handle_candidate_count,
            handle_constructed=handle_constructed,
            ocr_digit_obfuscation=ocr_digit_obfuscation,
            handle_from_binding=handle_from_binding,
        )

    @classmethod
    def from_slot(cls, slot_index: int, text: str) -> PlayerHandle | None:
        text = text.strip()
        if not text or text in _SKIP_LABELS:
            return None
        parts = parse_handle_parts(text)
        if parts is None:
            return None
        return cls(
            handle=parts.full,
            slot_index=slot_index,
            display_text=text,
            display_name=text if not is_valid_handle(text) else "",
            discriminator=parts.player_id,
            profile_id=parts.player_id,
            profile_ref=f"{parts.server_id}/{parts.realm_id}/{parts.player_id}",
            server_id=parts.server_id,
            realm_id=parts.realm_id,
        )


_SKIP_LABELS = frozenset(
    {
        "",
        "开放",
        "Open",
        "Closed",
        "关闭",
        "电脑",
        "Computer",
        "A.I.",
    }
)
