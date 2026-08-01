from __future__ import annotations

import re
from dataclasses import dataclass

DEFAULT_FORMER_NAME_PREFIX = "曾用名"


def append_former_name(
    remark: str,
    former_name: str,
    *,
    prefix: str = DEFAULT_FORMER_NAME_PREFIX,
) -> str:
    former_name = former_name.strip()
    if not former_name:
        return remark.strip()
    tag = f"{prefix}: {former_name}"
    current = remark.strip()
    if tag in current or former_name == current:
        return current
    if re.search(rf"(?:^|;)\s*{re.escape(prefix)}\s*:\s*{re.escape(former_name)}\s*(?:;|$)", current):
        return current
    if current:
        return f"{current}; {tag}"
    return tag


@dataclass
class RosterMergeStats:
    remote_count: int = 0
    local_candidates: int = 0
    added: int = 0
    updated_names: int = 0
    unchanged: int = 0


def _row_key(row: dict[str, str]) -> str:
    return str(row.get("handle", "")).strip()


def merge_roster_with_local(
    remote_rows: list[dict[str, str]],
    local_rows: list[dict[str, str]],
    *,
    former_name_prefix: str = DEFAULT_FORMER_NAME_PREFIX,
) -> tuple[list[dict[str, str]], RosterMergeStats]:
    """Merge remote document rows with local candidates; handle is unique key."""
    stats = RosterMergeStats(
        remote_count=len(remote_rows),
        local_candidates=len(local_rows),
    )

    merged_order: list[str] = []
    merged: dict[str, dict[str, str]] = {}

    for row in remote_rows:
        handle = _row_key(row)
        if not handle:
            continue
        if handle in merged:
            continue
        merged[handle] = {
            "display_name": str(row.get("display_name", "")).strip(),
            "handle": handle,
            "remark": str(row.get("remark", "")).strip(),
        }
        merged_order.append(handle)

    local_by_handle: dict[str, dict[str, str]] = {}
    for row in local_rows:
        handle = _row_key(row)
        if not handle:
            continue
        local_by_handle[handle] = {
            "display_name": str(row.get("display_name", "")).strip(),
            "handle": handle,
            "remark": str(row.get("remark", "")).strip(),
        }

    for handle, local in local_by_handle.items():
        remote = merged.get(handle)
        if remote is None:
            merged[handle] = dict(local)
            merged_order.append(handle)
            stats.added += 1
            continue

        local_name = local["display_name"]
        remote_name = remote["display_name"]
        if local_name and local_name != remote_name:
            remote["display_name"] = local_name
            if remote_name:
                remote["remark"] = append_former_name(
                    local["remark"] or remote["remark"],
                    remote_name,
                    prefix=former_name_prefix,
                )
            elif local["remark"]:
                remote["remark"] = local["remark"]
            stats.updated_names += 1
        elif local["remark"] and local["remark"] != remote["remark"]:
            remote["remark"] = local["remark"]
            stats.unchanged += 1
        else:
            stats.unchanged += 1

    result = [merged[handle] for handle in merged_order if handle in merged]
    return result, stats
