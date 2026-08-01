from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class PlayerRosterEntry:
    handle: str
    display_name: str = ""
    remark: str = ""
    updated_at: datetime | None = None
    source: str = "manual"
