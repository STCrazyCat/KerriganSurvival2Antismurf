import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.config.settings import AppConfig, save_user_calibration
from antismurf.review.profile_parser import parse_profile_ids_text


def test_parse_profile_url():
    ref = parse_profile_ids_text(
        "https://starcraft2.com/en-us/profile/1/1/6615271"
    )
    assert ref is not None
    assert ref.region_id == 1
    assert ref.realm_id == 1
    assert ref.profile_id == 6615271


def test_parse_profile_ids_slash():
    ref = parse_profile_ids_text("1/1/6615271")
    assert ref is not None
    assert ref.profile_id == 6615271


def test_save_user_calibration(tmp_path, monkeypatch):
    from antismurf.config import settings

    monkeypatch.setattr(settings, "_project_root", lambda: tmp_path)
    (tmp_path / "config").mkdir()

    cfg = AppConfig(
        host_handle="5-S2-1-1234",
        slot_regions=[{"x": 0.12, "y": 0.35}],
    )
    path = save_user_calibration(cfg)
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "5-S2-1-1234" in text
    assert "slot_regions" in text
