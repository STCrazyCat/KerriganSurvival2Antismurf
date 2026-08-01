import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.vision.lobby_text_parser import parse_lobby_identity


def test_parse_team_and_id() -> None:
    identity = parse_lobby_identity("<#某战队>#6738824")
    assert identity is not None
    assert identity.profile_id == 6738824
    assert identity.team == "某战队"


def test_parse_hash_id() -> None:
    identity = parse_lobby_identity("#6738824")
    assert identity is not None
    assert identity.profile_id == 6738824


def test_parse_plain_digits() -> None:
    identity = parse_lobby_identity("12208616")
    assert identity is not None
    assert identity.profile_id == 12208616


def test_parse_full_handle() -> None:
    identity = parse_lobby_identity("5-S2-1-6738824")
    assert identity is not None
    assert identity.handle == "5-S2-1-6738824"
    assert identity.profile_id == 6738824


def test_parse_normalizes_fullwidth() -> None:
    identity = parse_lobby_identity("＜#战队＞＃6738824")
    assert identity is not None
    assert identity.profile_id == 6738824
