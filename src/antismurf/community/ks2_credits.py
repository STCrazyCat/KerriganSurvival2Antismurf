"""194823.xyz credits / redemption command API."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

DEFAULT_KS2_TOOL_BASE_URL = "https://194823.xyz"


@dataclass(frozen=True)
class Ks2CreditsInfo:
    handle: str
    replay_credits: int
    redemption_code: str
    penalty: int = 0
    updated: float | None = None

    @property
    def net_credits(self) -> int:
        return max(0, self.replay_credits - self.penalty)


def fetch_ks2_credits(
    handle: str,
    *,
    base_url: str = DEFAULT_KS2_TOOL_BASE_URL,
    timeout_sec: float = 15.0,
) -> Ks2CreditsInfo:
    """Query upload credits and redemption command for a SC2 handle."""
    handle = handle.strip()
    if not handle:
        raise ValueError("handle is required")

    url = f"{base_url.rstrip('/')}/api/credits"
    response = httpx.get(
        url,
        params={"player_handle": handle},
        timeout=timeout_sec,
        headers={"Accept": "application/json"},
    )
    if response.status_code == 400:
        payload = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        message = payload.get("error") if isinstance(payload, dict) else response.text
        raise ValueError(str(message or "invalid handle"))
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("unexpected credits response")

    code = str(data.get("code", "")).strip()
    if not code:
        raise ValueError("credits response missing redemption code")

    replays = int(data.get("replays", 0) or 0)
    penalty = int(data.get("penalty", 0) or 0)
    updated_raw = data.get("updated")
    updated = float(updated_raw) if updated_raw is not None else None
    return Ks2CreditsInfo(
        handle=handle,
        replay_credits=replays,
        redemption_code=code,
        penalty=penalty,
        updated=updated,
    )
