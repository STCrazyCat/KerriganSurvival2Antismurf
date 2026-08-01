from __future__ import annotations

from antismurf.config.settings import AppConfig
from antismurf.models.player import parse_handle_parts
from antismurf.vision.lobby_text_parser import LobbyIdentity

# Re-export resolution API; legacy imports may use handle_resolver.resolve_handle.


def local_profile_id(config: AppConfig) -> int | None:
    from antismurf.models.player import parse_handle_parts as _parse

    handle = (config.host_handle or "").strip()
    if not handle:
        return None
    parts = _parse(handle)
    return parts.player_id if parts else None


def default_region_realm(config: AppConfig) -> tuple[int, int]:
    handle = (config.host_handle or "").strip()
    if handle:
        parts = parse_handle_parts(handle)
        if parts is not None:
            return parts.server_id, parts.realm_id
    return 5, 1


def construct_handle(profile_id: int, config: AppConfig) -> str:
    region_id, realm_id = default_region_realm(config)
    return f"{region_id}-S2-{realm_id}-{profile_id}"


def resolve_handle(
    identity: LobbyIdentity,
    config: AppConfig,
    roster_store=None,
) -> str | None:
    from antismurf.vision.handle_resolution import resolve_handle_detailed

    return resolve_handle_detailed(identity, config, roster_store).handle
