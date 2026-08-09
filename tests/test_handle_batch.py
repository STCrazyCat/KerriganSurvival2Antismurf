import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.models.player import parse_handle_batch


def test_split_on_spaces_commas_semicolons() -> None:
    text = "5-S2-1-1234567, 5-S2-1-7654321；5-S2-1-1111、5-S2-1-2222; 5-S2-1-3333"
    valid, invalid = parse_handle_batch(text)
    assert valid == [
        "5-S2-1-1234567",
        "5-S2-1-7654321",
        "5-S2-1-1111",
        "5-S2-1-2222",
        "5-S2-1-3333",
    ]
    assert invalid == []


def test_newline_split() -> None:
    text = "5-S2-1-1234567\n5-S2-1-7654321\n\n5-S2-1-9999"
    valid, invalid = parse_handle_batch(text)
    assert valid == ["5-S2-1-1234567", "5-S2-1-7654321", "5-S2-1-9999"]
    assert invalid == []


def test_bare_numbers_auto_completed() -> None:
    valid, invalid = parse_handle_batch("1234567 8888888 42")
    assert valid == ["5-S2-1-1234567", "5-S2-1-8888888", "5-S2-1-42"]
    assert invalid == []


def test_mixed_full_and_bare() -> None:
    valid, invalid = parse_handle_batch("5-S2-1-1234567, 7654321")
    assert valid == ["5-S2-1-1234567", "5-S2-1-7654321"]
    assert invalid == []


def test_invalid_items_flagged() -> None:
    valid, invalid = parse_handle_batch("5-S2-1-1234567 abc 5-S2-x-1-99999 12a")
    assert valid == ["5-S2-1-1234567"]
    assert invalid == ["abc", "5-S2-x-1-99999", "12a"]


def test_empty_input() -> None:
    valid, invalid = parse_handle_batch("   , ，  \n  ")
    assert valid == []
    assert invalid == []


def test_custom_prefix() -> None:
    valid, _ = parse_handle_batch("123 456", default_prefix="6-S2-2-")
    assert valid == ["6-S2-2-123", "6-S2-2-456"]
