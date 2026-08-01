"""Local SC2 replay auto-upload."""

from antismurf.replay.auto_upload import ReplayAutoUploader
from antismurf.replay.paths import resolve_replay_upload_paths
from antismurf.replay.uploader import UploadResult, upload_replay

__all__ = [
    "ReplayAutoUploader",
    "UploadResult",
    "resolve_replay_upload_paths",
    "upload_replay",
]
