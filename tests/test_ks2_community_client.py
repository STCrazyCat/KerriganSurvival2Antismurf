import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.community.factory import create_community_provider
from antismurf.community.ks2_endpoints import (
    KS2_TOOL194823_BASE_URL,
    KS2_TOOL194823_ENDPOINTS,
    KS2_WIKI_ENDPOINTS,
    endpoints_for_base_url,
)
from antismurf.config.settings import AppConfig


def test_endpoints_for_base_url():
    assert endpoints_for_base_url("https://wiki.ks2.top") == KS2_WIKI_ENDPOINTS
    assert endpoints_for_base_url("https://194823.xyz") == KS2_TOOL194823_ENDPOINTS


def test_factory_194823_provider():
    cfg = AppConfig(community_provider="194823")
    provider = create_community_provider(cfg)
    assert provider._base == KS2_TOOL194823_BASE_URL
    assert provider._endpoints.mmr_param == "player_handle"


def test_194823_client_uses_wiki_for_playlike():
    from antismurf.community.ks2_wiki_client import Ks2CommunityClient

    mmr_payload = {"cores": {"survivor": 1607, "kerrigan": 2099}}
    playlike_payload = {
        "games": [{"role": "Energizer", "team": 0, "played_like": 2200.0}]
    }

    client = Ks2CommunityClient(base_url=KS2_TOOL194823_BASE_URL)

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, **kwargs):
            mock_resp = type("Resp", (), {})()
            mock_resp.status_code = 200
            mock_resp.text = "{}"
            if "/api/player" in url:
                mock_resp.json = lambda: mmr_payload
            elif "/api/played_like" in url:
                mock_resp.json = lambda: playlike_payload
            else:
                mock_resp.status_code = 404
                mock_resp.json = lambda: {}
            return mock_resp

    async def run():
        with patch("httpx.AsyncClient", return_value=FakeClient()):
            return await client.get_rating_by_handle("5-S2-1-6738824")

    rating = asyncio.run(run())
    assert rating.profile is not None
    assert rating.profile.core_mmr.survivor == 1607
    assert rating.profile.derived.data_quality.playlike_game_count == 1
