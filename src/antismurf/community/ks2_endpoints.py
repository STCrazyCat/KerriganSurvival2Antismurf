"""KS2 community server HTTP endpoint profiles.

Both https://wiki.ks2.top and https://194823.xyz front the same MMR backend.
Player pages are SPAs; data comes from JSON APIs (not HTML parsing).

wiki.ks2.top
  GET /api/mmr?handle={handle}
  GET /api/played_like?handle={handle}

194823.xyz (tool site)
  GET /api/player?player_handle={handle}   # same MMR payload as /api/mmr
  (no local played_like route — fall back to wiki for playlike games)
"""

from __future__ import annotations

from dataclasses import dataclass

KS2_WIKI_BASE_URL = "https://wiki.ks2.top"
KS2_TOOL194823_BASE_URL = "https://194823.xyz"

MMR_PATH_WIKI = "/api/mmr"
PLAYED_LIKE_PATH = "/api/played_like"
MMR_PATH_TOOL194823 = "/api/player"


@dataclass(frozen=True)
class Ks2EndpointProfile:
    """Query-string parameter names differ between hosts."""

    mmr_path: str
    mmr_param: str = "handle"
    played_like_path: str | None = PLAYED_LIKE_PATH
    played_like_param: str = "handle"
    played_like_base: str | None = None


KS2_WIKI_ENDPOINTS = Ks2EndpointProfile(
    mmr_path=MMR_PATH_WIKI,
    mmr_param="handle",
    played_like_path=PLAYED_LIKE_PATH,
    played_like_param="handle",
)

KS2_TOOL194823_ENDPOINTS = Ks2EndpointProfile(
    mmr_path=MMR_PATH_TOOL194823,
    mmr_param="player_handle",
    played_like_path=PLAYED_LIKE_PATH,
    played_like_param="handle",
    played_like_base=KS2_WIKI_BASE_URL,
)


def endpoints_for_base_url(base_url: str) -> Ks2EndpointProfile:
    host = base_url.rstrip("/").lower()
    if "194823.xyz" in host:
        return KS2_TOOL194823_ENDPOINTS
    return KS2_WIKI_ENDPOINTS
