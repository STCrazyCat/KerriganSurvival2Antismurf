import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.lobby.probe_calibration import CalibratedProfile, save_profile, load_profile
from antismurf.lobby.probe_session_log import (
    CeReference,
    ProbeSessionLog,
    compare_with_ce,
    parse_hex_address,
)


def test_parse_hex_address() -> None:
    assert parse_hex_address("0x1C1D795B720") == 0x1C1D795B720
    assert parse_hex_address("1C1FF9E9848") == 0x1C1FF9E9848


def test_compare_with_ce_match() -> None:
    rows = compare_with_ce(
        tool_name=0x1C1D795B720,
        tool_handle=0x1C1FF9E9848,
        ce_ref=CeReference(
            name_address=0x1C1D795B720,
            handle_address=0x1C1FF9E9848,
        ),
    )
    assert len(rows) == 2
    assert all(row.match for row in rows)


def test_compare_with_ce_mismatch() -> None:
    rows = compare_with_ce(
        tool_name=0x1000,
        tool_handle=0x2000,
        ce_ref=CeReference(name_address=0x1C1D795B720, handle_address=0x1C1FF9E9848),
        tolerance=0,
    )
    assert not rows[0].match
    assert rows[0].delta == 0x1000 - 0x1C1D795B720


def test_session_log_snapshot_and_export(tmp_path) -> None:
    log = ProbeSessionLog(log_dir=tmp_path)
    snap = log.update_snapshot(
        mode="scan",
        expected_name="大主教阿塔尼斯",
        expected_handle="5-S2-1-6738824",
        tool_name_address=0x1C1D795B720,
        tool_handle_address=0x1C1FF9E9848,
        name_live_ok=True,
        handle_live_ok=True,
        ce_ref=CeReference(name_address=0x1C1D795B720, handle_address=0x1C1FF9E9848),
    )
    assert snap.confirmed
    json_path = log.export_json()
    txt_path = log.export_text()
    assert json_path.exists()
    assert txt_path.exists()
    assert "CE 对照" in txt_path.read_text(encoding="utf-8")


def test_calibration_profile_roundtrip(tmp_path, monkeypatch) -> None:
    path = tmp_path / "probe_calibration.json"
    monkeypatch.setattr(
        "antismurf.lobby.probe_calibration.default_profile_path",
        lambda: path,
    )
    profile = CalibratedProfile(
        expected_handle="5-S2-1-6738824",
        expected_name="大主教阿塔尼斯",
        name_address=0x1C1D795B720,
        handle_address=0x1C1FF9E9848,
        source_mode="trace",
    )
    save_profile(profile, path)
    loaded = load_profile(path)
    assert loaded is not None
    assert loaded.name_address == profile.name_address
    assert loaded.resolved_handle_address() == profile.handle_address
