from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import httpx

from antismurf.config.settings import AppConfig
from antismurf.replay.parser import parse_replay_file

logger = logging.getLogger(__name__)

KS_REPLAY_UPLOAD_URL = "https://replay.kerrigansurvival.com/upload"
KS_REPLAY_MAGIC_HEADER = bytes(
    [0x4D, 0x50, 0x51, 0x1B, 0x00, 0x02, 0x00, 0x00, 0x00, 0x04]
)
DEFAULT_MAX_REPLAY_BYTES = 3 * 1024 * 1024
DEFAULT_USER_AGENT = "kerrigan-survival-uploader/1.07"


@dataclass(frozen=True)
class UploadResult:
    path: Path
    ok: bool
    status_code: int | None = None
    error: str | None = None


def replay_fingerprint(path: Path) -> str:
    stat = path.stat()
    return f"{path.resolve()}:{stat.st_size}:{int(stat.st_mtime)}"


def has_upload_magic_header(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            header = handle.read(len(KS_REPLAY_MAGIC_HEADER))
    except OSError as exc:
        logger.debug("Could not read replay header for %s: %s", path, exc)
        return False
    return header == KS_REPLAY_MAGIC_HEADER


def is_valid_upload_candidate(
    path: Path,
    *,
    max_bytes: int = DEFAULT_MAX_REPLAY_BYTES,
    min_age_sec: float = 5.0,
) -> bool:
    if path.suffix.lower() != ".sc2replay":
        return False
    try:
        stat = path.stat()
    except OSError:
        return False
    if stat.st_size <= 0 or stat.st_size > max_bytes:
        return False
    import time

    if time.time() - stat.st_mtime < min_age_sec:
        return False
    return has_upload_magic_header(path)


def is_ks2_replay_filename(
    path: Path,
    markers: tuple[str, ...] | list[str],
) -> bool:
    name = path.name
    for marker in markers:
        token = marker.strip()
        if token and token in name:
            return True
    return False


def is_ks2_replay(path: Path, config: AppConfig) -> bool:
    if is_ks2_replay_filename(path, config.replay_upload_filename_markers):
        return True
    if config.replay_upload_use_filename_filter:
        return False
    try:
        entries = parse_replay_file(path, config, ks2_only=True)
    except Exception as exc:
        logger.debug("KS2 replay parse failed for %s: %s", path, exc)
        return False
    return bool(entries)


def upload_replay(path: Path, config: AppConfig) -> UploadResult:
    if not is_valid_upload_candidate(
        path,
        max_bytes=config.replay_upload_max_bytes,
        min_age_sec=config.replay_upload_min_age_sec,
    ):
        return UploadResult(path=path, ok=False, error="录像未通过上传校验")

    if config.replay_upload_ks2_only and not is_ks2_replay(path, config):
        return UploadResult(path=path, ok=False, error="非 KS2 录像")

    url = config.replay_upload_url or KS_REPLAY_UPLOAD_URL
    user_agent = config.replay_upload_user_agent or DEFAULT_USER_AGENT

    try:
        with path.open("rb") as handle:
            response = httpx.post(
                url,
                content=handle.read(),
                headers={"User-Agent": user_agent},
                timeout=config.replay_upload_timeout_sec,
            )
    except Exception as exc:
        logger.warning("Replay upload failed for %s: %s", path.name, exc)
        return UploadResult(path=path, ok=False, error=str(exc))

    if response.status_code != 200:
        logger.warning(
            "Replay upload rejected for %s: HTTP %s",
            path.name,
            response.status_code,
        )
        return UploadResult(
            path=path,
            ok=False,
            status_code=response.status_code,
            error=f"HTTP {response.status_code}",
        )

    logger.info("Uploaded KS replay: %s", path.name)
    return UploadResult(path=path, ok=True, status_code=200)
