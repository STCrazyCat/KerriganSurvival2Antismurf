from __future__ import annotations



import json

import logging

import time

from pathlib import Path



from antismurf.config.settings import AppConfig, _project_root

from antismurf.replay.paths import (

    iter_replay_files_under,

    resolve_replay_upload_paths,

)

from antismurf.replay.uploader import (

    UploadResult,

    is_ks2_replay,

    is_valid_upload_candidate,

    replay_fingerprint,

    upload_replay,

)



logger = logging.getLogger(__name__)





class ReplayAutoUploader:

    """Upload recent KS2 replays (48h window) without duplicates; also after lobby exit."""



    def __init__(self, config: AppConfig) -> None:

        self._config = config

        self._local_handle: str | None = None

        self._session_started_at: float | None = None

        self._grace_until: float = 0.0

        self._last_periodic_check_at: float = 0.0

        self._last_grace_check_at: float = 0.0

        self._uploaded_keys: set[str] = set()

        self._state_path = _project_root() / "data" / "replay_upload_state.json"

        self._load_state()



    @property

    def enabled(self) -> bool:

        return self._config.replay_upload_enabled



    def set_local_handle(self, local_handle: str | None) -> None:

        self._local_handle = local_handle.strip() if local_handle else None



    def on_lobby_enter(self) -> None:

        self._session_started_at = time.time()

        self._grace_until = 0.0

        self._last_grace_check_at = 0.0

        logger.debug("KS2 replay upload session started")



    def on_lobby_exit(self) -> None:

        if self._session_started_at is None and self._grace_until <= time.time():

            return

        self._grace_until = time.time() + self._config.replay_upload_grace_sec

        self._last_grace_check_at = 0.0

        logger.info(

            "Lobby exited; watching for new replay for %.0fs (check every %.0fs)",

            self._config.replay_upload_grace_sec,

            self._config.replay_upload_grace_check_interval_sec,

        )



    def should_check_session(self) -> bool:

        if not self.enabled:

            return False

        if self._session_started_at is not None:

            return True

        return time.time() < self._grace_until



    def should_run_grace_check(self) -> bool:

        if not self.enabled:

            return False

        if time.time() >= self._grace_until:

            return False

        interval = self._config.replay_upload_grace_check_interval_sec

        return time.time() - self._last_grace_check_at >= interval



    def should_run_periodic(self) -> bool:

        if not self.enabled:

            return False

        interval = self._config.replay_upload_check_interval_sec

        return time.time() - self._last_periodic_check_at >= interval



    def should_run_check(self) -> bool:

        return (

            self.should_check_session()

            or self.should_run_periodic()

            or self.should_run_grace_check()

        )



    def check_and_upload(self) -> list[UploadResult]:

        if not self.enabled:

            return []



        results: list[UploadResult] = []



        if self.should_check_session() or self.should_run_grace_check():

            session_result = self._upload_session_replay()

            if session_result is not None:

                results.append(session_result)

            if self.should_run_grace_check():

                self._last_grace_check_at = time.time()



        if self.should_run_periodic():

            results.extend(self._upload_recent_replays())

            self._last_periodic_check_at = time.time()



        return results



    def preview(self) -> dict:

        handle = self._local_handle or self._config.host_handle or None

        search_paths = resolve_replay_upload_paths(

            self._config.replays_paths,

            handle,

        )

        pending = self._collect_candidates_in_window()

        return {

            "enabled": self.enabled,

            "session_active": self._session_started_at is not None,

            "grace_active": time.time() < self._grace_until,

            "grace_seconds_left": max(0.0, self._grace_until - time.time()),

            "uploaded_count": len(self._uploaded_keys),

            "window_hours": self._config.replay_upload_window_hours,

            "pending_in_window": len(pending),

            "search_paths": search_paths,

            "filename_markers": list(self._config.replay_upload_filename_markers),

        }



    def upload_now(self) -> list[UploadResult]:

        """Upload session replay and all pending files in the time window."""

        if not self.enabled:

            return []

        results: list[UploadResult] = []

        session = self._upload_session_replay()

        if session is not None:

            results.append(session)

        results.extend(self._upload_recent_replays())

        return results



    def latest_candidate_path(self) -> Path | None:

        candidates = self._collect_candidates_in_window()

        return candidates[-1] if candidates else None



    def _upload_session_replay(self) -> UploadResult | None:

        since = self._session_started_at

        if since is None and time.time() < self._grace_until:

            since = self._grace_until - self._config.replay_upload_grace_sec

        if since is None:

            since = time.time() - self._config.replay_upload_grace_sec



        candidate = self._find_latest_replay_since(since)

        if candidate is None:

            self._maybe_clear_session()

            return None



        fingerprint = replay_fingerprint(candidate)

        if fingerprint in self._uploaded_keys:

            self._finish_session()

            return None



        result = upload_replay(candidate, self._config)

        if result.ok:

            self._uploaded_keys.add(fingerprint)

            self._save_state()

            self._finish_session()

            logger.info("Uploaded session replay: %s", candidate.name)

        return result



    def _upload_recent_replays(self) -> list[UploadResult]:

        results: list[UploadResult] = []

        for path in self._collect_candidates_in_window():

            fingerprint = replay_fingerprint(path)

            if fingerprint in self._uploaded_keys:

                continue

            result = upload_replay(path, self._config)

            results.append(result)

            if result.ok:

                self._uploaded_keys.add(fingerprint)

                self._save_state()

                logger.info("Uploaded KS2 replay: %s", path.name)

            elif result.status_code and result.status_code != 200:

                logger.warning(

                    "Stopping upload batch after HTTP %s for %s",

                    result.status_code,

                    path.name,

                )

                break

        return results



    def _collect_candidates_in_window(self) -> list[Path]:

        window_sec = self._config.replay_upload_window_hours * 3600.0

        cutoff = time.time() - window_sec

        now = time.time()

        handle = self._local_handle or self._config.host_handle or None

        search_paths = resolve_replay_upload_paths(

            self._config.replays_paths,

            handle,

        )



        by_path: dict[Path, float] = {}

        for raw in search_paths:

            root = Path(raw)

            for path in iter_replay_files_under(root):

                try:

                    mtime = path.stat().st_mtime

                except OSError:

                    continue

                if mtime < cutoff or mtime > now + 1:

                    continue

                if not is_valid_upload_candidate(

                    path,

                    max_bytes=self._config.replay_upload_max_bytes,

                    min_age_sec=self._config.replay_upload_min_age_sec,

                ):

                    continue

                if self._config.replay_upload_ks2_only and not is_ks2_replay(

                    path, self._config

                ):

                    continue

                existing = by_path.get(path)

                if existing is None or mtime > existing:

                    by_path[path] = mtime



        return [

            path

            for path, _ in sorted(by_path.items(), key=lambda item: item[1])

        ]



    def _find_latest_replay_since(self, since: float) -> Path | None:

        latest: Path | None = None

        latest_mtime = since

        for path in self._collect_candidates_in_window():

            try:

                mtime = path.stat().st_mtime

            except OSError:

                continue

            if mtime + 1 < since:

                continue

            if mtime >= latest_mtime:

                latest = path

                latest_mtime = mtime

        return latest



    def _finish_session(self) -> None:

        self._session_started_at = None

        self._grace_until = 0.0



    def _maybe_clear_session(self) -> None:

        if self._session_started_at is None and time.time() >= self._grace_until:

            return

        if time.time() < self._grace_until:

            return

        logger.debug("Replay upload grace period expired without a new replay")

        self._finish_session()



    def _load_state(self) -> None:

        if not self._state_path.exists():

            return

        try:

            data = json.loads(self._state_path.read_text(encoding="utf-8"))

        except (OSError, json.JSONDecodeError) as exc:

            logger.warning("Could not load replay upload state: %s", exc)

            return

        uploaded = data.get("uploaded", [])

        if isinstance(uploaded, list):

            self._uploaded_keys = {str(item) for item in uploaded}



    def _save_state(self) -> None:

        self._state_path.parent.mkdir(parents=True, exist_ok=True)

        payload = {

            "uploaded": sorted(self._uploaded_keys)[-2000:],

            "updated_at": int(time.time()),

        }

        self._state_path.write_text(

            json.dumps(payload, indent=2),

            encoding="utf-8",

        )


