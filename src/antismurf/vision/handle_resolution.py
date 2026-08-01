from __future__ import annotations

from dataclasses import dataclass

from antismurf.config.settings import AppConfig
from antismurf.models.player import parse_handle_parts
from antismurf.roster.parser import normalize_display_name
from antismurf.roster.store import PlayerRosterStore
from antismurf.vision.lobby_text_parser import LobbyIdentity, digit_obfuscation_suspected


@dataclass(frozen=True)
class HandleResolution:
    handle: str | None
    ambiguous: bool = False
    candidate_count: int = 0
    constructed: bool = False
    from_binding: bool = False
    digit_obfuscation: bool = False
    resolved: bool = False


def resolve_handle_detailed(
    identity: LobbyIdentity,
    config: AppConfig,
    roster_store: PlayerRosterStore | None = None,
) -> HandleResolution:
    obfuscation = identity.digit_obfuscation or digit_obfuscation_suspected(
        identity.raw_text
    )

    if identity.handle and parse_handle_parts(identity.handle):
        return HandleResolution(
            handle=identity.handle,
            candidate_count=1,
            resolved=True,
            digit_obfuscation=obfuscation,
        )

    profile_id = identity.profile_id
    if profile_id is None:
        if roster_store and identity.display_name:
            entry = roster_store.get_by_display_name(
                normalize_display_name(identity.display_name)
            )
            if entry:
                return HandleResolution(
                    handle=entry.handle,
                    candidate_count=1,
                    from_binding=True,
                    resolved=True,
                    digit_obfuscation=obfuscation,
                )
        return HandleResolution(
            handle=None,
            candidate_count=0,
            digit_obfuscation=obfuscation,
            resolved=False,
        )

    if roster_store is not None:
        entry = roster_store.get_by_profile_id(profile_id)
        if entry:
            return HandleResolution(
                handle=entry.handle,
                candidate_count=1,
                from_binding=True,
                resolved=True,
                digit_obfuscation=obfuscation,
            )
        if identity.display_name:
            entry = roster_store.get_by_display_name(
                normalize_display_name(identity.display_name)
            )
            if entry:
                return HandleResolution(
                    handle=entry.handle,
                    candidate_count=1,
                    from_binding=True,
                    resolved=True,
                    digit_obfuscation=obfuscation,
                )

    from antismurf.vision.handle_resolver import construct_handle

    return HandleResolution(
        handle=construct_handle(profile_id, config),
        candidate_count=1,
        constructed=True,
        resolved=True,
        digit_obfuscation=obfuscation,
    )


def resolve_handle(
    identity: LobbyIdentity,
    config: AppConfig,
    roster_store: PlayerRosterStore | None = None,
) -> str | None:
    return resolve_handle_detailed(identity, config, roster_store).handle
