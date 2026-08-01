from __future__ import annotations

import re
from dataclasses import dataclass

# starcraft2.com/en-us/profile/1/1/6615271
# battle.net/sc2/en/profile/64660/2/...
PROFILE_URL_PATTERN = re.compile(
    r"/profile/(\d+)/(\d+)/(\d+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Sc2ProfileRef:
    region_id: int
    realm_id: int
    profile_id: int


def parse_profile_url(url: str) -> Sc2ProfileRef | None:
    match = PROFILE_URL_PATTERN.search(url.strip())
    if not match:
        return None
    return Sc2ProfileRef(
        region_id=int(match.group(1)),
        realm_id=int(match.group(2)),
        profile_id=int(match.group(3)),
    )


def parse_profile_ids_text(text: str) -> Sc2ProfileRef | None:
    text = text.strip()
    ref = parse_profile_url(text)
    if ref:
        return ref
    parts = [p.strip() for p in text.replace(",", "/").split("/") if p.strip()]
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        return Sc2ProfileRef(
            region_id=int(parts[0]),
            realm_id=int(parts[1]),
            profile_id=int(parts[2]),
        )
    return None
