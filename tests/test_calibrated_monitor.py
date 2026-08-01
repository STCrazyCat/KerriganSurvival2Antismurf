import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.lobby.calibrated_monitor import CalibratedMonitorSession
from antismurf.lobby.probe_calibration import CalibratedProfile


def test_calibrated_monitor_tick_ok(monkeypatch) -> None:
    profile = CalibratedProfile(
        expected_handle="5-S2-1-6738824",
        expected_name="大主教阿塔尼斯",
        name_address=0x1000,
        handle_address=0x2000,
    )

    monkeypatch.setattr(
        "antismurf.lobby.probe_calibration.verify_name_bytes_at",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        "antismurf.lobby.probe_calibration.verify_handle_bytes_at",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        "antismurf.lobby.calibrated_monitor.build_module_map",
        lambda pid: [],
    )
    monkeypatch.setattr(
        "antismurf.lobby.calibrated_monitor.locate_address",
        lambda address, **kwargs: type(
            "Loc",
            (),
            {"module_label": hex(address), "region_type": "private"},
        )(),
    )

    session = CalibratedMonitorSession(None, pid=1, profile=profile)
    result = session.tick()
    assert result.status == "ok"
    assert result.reading.all_ok
    assert session.stats.ok_ticks == 1
