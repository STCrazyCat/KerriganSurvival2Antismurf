from __future__ import annotations

from antismurf.roster.store import PlayerRosterStore


def collect_local_candidates(
    store: PlayerRosterStore,
    *,
    include_replays: bool = True,
) -> list[dict[str, str]]:
    """Build local rows keyed by handle for bidirectional roster sync."""
    by_handle: dict[str, dict[str, str]] = {}

    for entry in store.list_all():
        if not entry.handle:
            continue
        by_handle[entry.handle] = {
            "handle": entry.handle,
            "display_name": entry.display_name.strip(),
            "remark": entry.remark.strip(),
        }

    return list(by_handle.values())
