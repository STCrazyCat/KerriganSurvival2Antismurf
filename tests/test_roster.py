import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.config.settings import AppConfig
from antismurf.roster.models import PlayerRosterEntry
from antismurf.roster.parser import normalize_display_name, parse_csv_file, parse_roster_rows
from antismurf.roster.store import PlayerRosterStore
from antismurf.vision.handle_resolver import resolve_handle
from antismurf.vision.lobby_text_parser import LobbyIdentity


def test_normalize_display_name() -> None:
    assert normalize_display_name("<#战队>#玩家A") == "玩家A"
    assert normalize_display_name("#1234") == "1234"


def test_parse_csv_and_upsert(tmp_path: Path) -> None:
    csv_path = tmp_path / "roster.csv"
    csv_path.write_text(
        "玩家名,句柄,备注\n老朋友,5-S2-1-1000001,常来玩\n",
        encoding="utf-8-sig",
    )
    entries = parse_csv_file(csv_path)
    assert len(entries) == 1
    assert entries[0].handle == "5-S2-1-1000001"
    assert entries[0].remark == "常来玩"

    db_path = tmp_path / "roster.db"
    store = PlayerRosterStore(db_path)
    store.init()
    store.upsert_batch(entries)
    loaded = store.get_by_handle("5-S2-1-1000001")
    assert loaded is not None
    assert loaded.display_name == "老朋友"


def test_display_name_ambiguity_returns_none(tmp_path: Path) -> None:
    db_path = tmp_path / "roster.db"
    store = PlayerRosterStore(db_path)
    store.init()
    store.upsert_batch(
        [
            PlayerRosterEntry(handle="5-S2-1-1", display_name="同名"),
            PlayerRosterEntry(handle="5-S2-1-2", display_name="同名"),
        ]
    )
    assert store.get_by_display_name("同名") is None


def test_resolve_handle_from_roster(tmp_path: Path) -> None:
    store = PlayerRosterStore(tmp_path / "roster.db")
    store.init()
    store.upsert_batch(
        [PlayerRosterEntry(handle="5-S2-1-8888888", display_name="名册玩家")]
    )
    config = AppConfig(host_handle="5-S2-1-12208616")
    identity = LobbyIdentity(
        raw_text="名册玩家",
        display_name="名册玩家",
        profile_id=None,
    )
    assert resolve_handle(identity, config, store) == "5-S2-1-8888888"


def test_parse_roster_rows_skips_invalid_handle() -> None:
    rows = [
        {"display_name": "坏数据", "handle": "not-a-handle", "remark": ""},
        {"display_name": "好数据", "handle": "5-S2-1-42", "remark": "ok"},
    ]
    entries = parse_roster_rows(rows)
    assert len(entries) == 1
    assert entries[0].handle == "5-S2-1-42"
