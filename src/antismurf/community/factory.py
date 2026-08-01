from __future__ import annotations

from antismurf.community.disabled_provider import DisabledCommunityProvider
from antismurf.community.http_client import HttpCommunityClient
from antismurf.community.ks2_wiki_client import Ks2CommunityClient, Ks2WikiClient
from antismurf.community.protocol import CommunityProvider
from antismurf.community.stub_store import StubCommunityStore
from antismurf.config.settings import AppConfig


def community_provider_enabled(config: AppConfig) -> bool:
    provider = config.community_provider.strip().lower()
    return provider not in {"disabled", "off", "none", ""}


def create_community_provider(config: AppConfig) -> CommunityProvider:
    provider = config.community_provider.lower()
    if provider in {"disabled", "off", "none", ""}:
        return DisabledCommunityProvider()
    if provider in {"ks2wiki", "wiki", "ks2"}:
        base = config.community_base_url or "https://wiki.ks2.top"
        return Ks2CommunityClient(
            base_url=base,
            timeout_sec=config.community_timeout_sec,
        )
    if provider in {"194823", "tool194823", "ks2tool"}:
        base = config.community_base_url or "https://194823.xyz"
        return Ks2CommunityClient(
            base_url=base,
            timeout_sec=config.community_timeout_sec,
        )
    if provider == "http" and config.community_base_url:
        return HttpCommunityClient(
            base_url=config.community_base_url,
            submit_path=config.community_submit_path,
            rating_path=config.community_rating_path,
            api_key=config.community_api_key,
            timeout_sec=config.community_timeout_sec,
        )
    return StubCommunityStore(config.community_stub_path)
