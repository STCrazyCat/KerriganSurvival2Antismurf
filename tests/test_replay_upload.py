import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.config.settings import AppConfig
from antismurf.replay.auto_upload import ReplayAutoUploader
from antismurf.replay.uploader import (
    KS_REPLAY_MAGIC_HEADER,
    has_upload_magic_header,
    is_ks2_replay_filename,
    is_valid_upload_candidate,
    upload_replay,
)
from antismurf.replay.paths import (
    discover_multiplayer_replay_dirs,
    resolve_replay_upload_paths,
)


def test_has_upload_magic_header(tmp_path: Path) -> None:
    valid = tmp_path / "valid.SC2Replay"
    valid.write_bytes(KS_REPLAY_MAGIC_HEADER + b"rest")
    invalid = tmp_path / "invalid.SC2Replay"
    invalid.write_bytes(b"not-a-replay")

    assert has_upload_magic_header(valid)
    assert not has_upload_magic_header(invalid)


def test_is_valid_upload_candidate_checks_size_and_age(tmp_path: Path) -> None:
    replay = tmp_path / "game.SC2Replay"
    replay.write_bytes(KS_REPLAY_MAGIC_HEADER + b"x" * 64)

    assert not is_valid_upload_candidate(replay, min_age_sec=9999.0)
    old = time.time() - 60
    import os

    os.utime(replay, (old, old))
    assert is_valid_upload_candidate(replay, min_age_sec=5.0)


def test_upload_replay_posts_raw_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    replay = tmp_path / "ks2 凯瑞甘生存2.SC2Replay"
    body = KS_REPLAY_MAGIC_HEADER + b"payload"
    replay.write_bytes(body)
    old = time.time() - 60
    import os

    os.utime(replay, (old, old))

    replay_data = SimpleNamespace(
        map_name="凯瑞甘生存2",
        game_type="Custom",
        date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        players=[
            SimpleNamespace(name="5-S2-1-1001", type="User", result="Win"),
        ],
    )

    captured: dict = {}

    class FakeResponse:
        status_code = 200

    import antismurf.replay.parser as rp
    import antismurf.replay.uploader as up

    original_load = rp._load_replay
    rp._load_replay = lambda _path: replay_data

    def fake_post(url, *, content, headers, timeout):
        captured["url"] = url
        captured["content"] = content
        captured["headers"] = headers
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(up.httpx, "post", fake_post)
    try:
        config = AppConfig(
            replay_upload_url="https://replay.kerrigansurvival.com/upload",
            replay_upload_user_agent="kerrigan-survival-uploader/1.07",
        )
        result = upload_replay(replay, config)
    finally:
        rp._load_replay = original_load

    assert result.ok
    assert captured["url"] == "https://replay.kerrigansurvival.com/upload"
    assert captured["content"] == body
    assert captured["headers"]["User-Agent"] == "kerrigan-survival-uploader/1.07"


def test_is_ks2_replay_filename() -> None:
    assert is_ks2_replay_filename(
        Path("2026-01-01 凯瑞甘生存2 (123).SC2Replay"),
        ["凯瑞甘生存2"],
    )
    assert not is_ks2_replay_filename(
        Path("ladder.SC2Replay"),
        ["凯瑞甘生存2"],
    )


def test_discover_multiplayer_replay_dirs(tmp_path: Path) -> None:
    accounts = tmp_path / "Accounts"
    mp = (
        accounts
        / "504618438"
        / "5-S2-1-6738824"
        / "Replays"
        / "Multiplayer"
    )
    mp.mkdir(parents=True)
    found = discover_multiplayer_replay_dirs([accounts])
    assert found == [mp]


def test_resolve_replay_upload_paths_prefers_configured(tmp_path: Path) -> None:
    configured = tmp_path / "custom"
    configured.mkdir()
    paths = resolve_replay_upload_paths([str(configured)], local_handle=None)
    assert paths == [str(configured)]


def test_periodic_upload_skips_outside_window_and_duplicates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import os

    recent = tmp_path / "2026 凯瑞甘生存2 recent.SC2Replay"
    recent.write_bytes(KS_REPLAY_MAGIC_HEADER + b"recent")
    old_recent = time.time() - 3600
    os.utime(recent, (old_recent, old_recent))

    stale = tmp_path / "2026 凯瑞甘生存2 stale.SC2Replay"
    stale.write_bytes(KS_REPLAY_MAGIC_HEADER + b"stale")
    old_stale = time.time() - 72 * 3600
    os.utime(stale, (old_stale, old_stale))

    upload_calls: list[Path] = []

    def fake_upload(path: Path, config: AppConfig) -> object:
        upload_calls.append(path)
        from antismurf.replay.uploader import UploadResult

        return UploadResult(path=path, ok=True, status_code=200)

    monkeypatch.setattr(
        "antismurf.replay.auto_upload.upload_replay",
        fake_upload,
    )
    monkeypatch.setattr(
        "antismurf.replay.auto_upload.resolve_replay_upload_paths",
        lambda paths, handle: [str(tmp_path)],
    )

    state_path = tmp_path / "state.json"
    monkeypatch.setattr(ReplayAutoUploader, "_load_state", lambda self: None)

    def save_state(self) -> None:
        state_path.write_text(
            '{"uploaded": []}',
            encoding="utf-8",
        )

    monkeypatch.setattr(ReplayAutoUploader, "_save_state", save_state)

    config = AppConfig(
        replay_upload_enabled=True,
        replays_paths=[str(tmp_path)],
        replay_upload_window_hours=48.0,
        replay_upload_check_interval_sec=0.0,
    )
    uploader = ReplayAutoUploader(config)
    uploader._state_path = state_path
    uploader._last_periodic_check_at = 0.0

    first = uploader.check_and_upload()
    assert len(first) == 1
    assert upload_calls == [recent]

    second = uploader.check_and_upload()
    assert second == []
    assert len(upload_calls) == 1


def test_auto_uploader_uploads_once_after_lobby_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replay = tmp_path / "finished 凯瑞甘生存2.SC2Replay"
    replay.write_bytes(KS_REPLAY_MAGIC_HEADER + b"game")
    old = time.time() - 30
    import os

    os.utime(replay, (old, old))

    replay_data = SimpleNamespace(
        map_name="Kerrigan Survival 2",
        game_type="Custom",
        unix_timestamp=1700000000,
        players=[
            SimpleNamespace(name="5-S2-1-7777", type="User", result="Win"),
        ],
    )

    import antismurf.replay.parser as rp

    original_load = rp._load_replay
    rp._load_replay = lambda _path: replay_data

    upload_calls: list[Path] = []

    def fake_upload(path: Path, config: AppConfig) -> object:
        upload_calls.append(path)
        from antismurf.replay.uploader import UploadResult

        return UploadResult(path=path, ok=True, status_code=200)

    monkeypatch.setattr(
        "antismurf.replay.auto_upload.upload_replay",
        fake_upload,
    )
    monkeypatch.setattr(
        "antismurf.replay.auto_upload.resolve_replay_upload_paths",
        lambda paths, handle: [str(tmp_path)],
    )

    state_path = tmp_path / "state.json"
    monkeypatch.setattr(
        ReplayAutoUploader,
        "_load_state",
        lambda self: None,
    )

    def save_state(self) -> None:
        state_path.write_text('{"uploaded": []}', encoding="utf-8")

    monkeypatch.setattr(ReplayAutoUploader, "_save_state", save_state)

    try:
        config = AppConfig(
            replay_upload_enabled=True,
            replays_paths=[str(tmp_path)],
            replay_upload_grace_sec=120.0,
        )
        uploader = ReplayAutoUploader(config)
        uploader._state_path = state_path

        uploader.on_lobby_enter()
        uploader._session_started_at = time.time() - 120
        assert uploader.should_run_check()

        first = uploader.check_and_upload()
        assert len(first) == 1
        assert upload_calls == [replay]

        second = uploader.check_and_upload()
        assert second == []
        assert len(upload_calls) == 1
        assert not uploader.should_check_session()
    finally:
        rp._load_replay = original_load
