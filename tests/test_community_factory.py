import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.config.settings import AppConfig
from antismurf.community.factory import (
    community_provider_enabled,
    create_community_provider,
)


def test_factory_disabled_default():
    cfg = AppConfig()
    assert cfg.community_provider == "disabled"
    provider = create_community_provider(cfg)
    assert provider.__class__.__name__ == "DisabledCommunityProvider"
    assert not community_provider_enabled(cfg)


def test_factory_stub():
    cfg = AppConfig(community_provider="stub")
    provider = create_community_provider(cfg)
    assert provider.__class__.__name__ == "StubCommunityStore"
    assert community_provider_enabled(cfg)


def test_factory_http_when_configured():
    cfg = AppConfig(
        community_provider="http",
        community_base_url="https://example.com",
    )
    provider = create_community_provider(cfg)
    assert provider.__class__.__name__ == "HttpCommunityClient"


def test_factory_ks2wiki_default():
    cfg = AppConfig(community_provider="ks2wiki")
    provider = create_community_provider(cfg)
    assert provider.__class__.__name__ in ("Ks2WikiClient", "Ks2CommunityClient")
