import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.config.settings import AppConfig
from antismurf.vision.handle_resolver import construct_handle, resolve_handle
from antismurf.vision.lobby_text_parser import LobbyIdentity


def test_construct_handle_from_host_config() -> None:
    config = AppConfig(host_handle="5-S2-1-12208616")
    assert construct_handle(6738824, config) == "5-S2-1-6738824"


def test_resolve_handle_falls_back_to_construct() -> None:
    config = AppConfig(host_handle="5-S2-1-12208616")
    identity = LobbyIdentity(
        raw_text="#6738824",
        display_name="#6738824",
        profile_id=6738824,
    )
    assert resolve_handle(identity, config) == "5-S2-1-6738824"
