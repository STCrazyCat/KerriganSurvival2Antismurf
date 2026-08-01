"""SC2 replay directory discovery for auto-upload (handle-aware)."""

from __future__ import annotations

from pathlib import Path

from antismurf.models.player import is_valid_handle

REPLAY_SUFFIXES = {".sc2replay", ".SC2Replay"}


def iter_sc2_accounts_roots() -> list[Path]:
    """Standard SC2 Accounts folders (Documents and OneDrive)."""
    home = Path.home()
    candidates = [
        home / "Documents" / "StarCraft II" / "Accounts",
        home / "OneDrive" / "Documents" / "StarCraft II" / "Accounts",
    ]
    return [path for path in candidates if path.is_dir()]


def find_replay_roots_for_handle(handle: str) -> list[Path]:
    """Locate ``.../Accounts/<id>/<handle>/Replays[/Multiplayer]`` for this machine."""
    if not is_valid_handle(handle):
        return []

    roots: list[Path] = []
    seen: set[str] = set()
    for accounts_root in iter_sc2_accounts_roots():
        if not accounts_root.is_dir():
            continue
        for account_dir in sorted(accounts_root.iterdir()):
            if not account_dir.is_dir():
                continue
            handle_dir = account_dir / handle
            if not handle_dir.is_dir():
                continue
            replays_dir = handle_dir / "Replays"
            if not replays_dir.is_dir():
                continue
            multiplayer = replays_dir / "Multiplayer"
            target = multiplayer if multiplayer.is_dir() else replays_dir
            key = str(target.resolve())
            if key not in seen:
                seen.add(key)
                roots.append(target)
    return roots


def discover_multiplayer_replay_dirs(
    accounts_roots: list[Path] | None = None,
) -> list[Path]:
    """Find all ``.../Accounts/<id>/<handle>/Replays/Multiplayer`` directories."""
    roots = accounts_roots or iter_sc2_accounts_roots()
    found: list[Path] = []
    seen: set[str] = set()
    for accounts_root in roots:
        if not accounts_root.is_dir():
            continue
        for account_dir in sorted(accounts_root.iterdir()):
            if not account_dir.is_dir():
                continue
            for handle_dir in sorted(account_dir.iterdir()):
                if not handle_dir.is_dir():
                    continue
                multiplayer = handle_dir / "Replays" / "Multiplayer"
                if not multiplayer.is_dir():
                    continue
                key = str(multiplayer.resolve())
                if key in seen:
                    continue
                seen.add(key)
                found.append(multiplayer)
    return found


def default_replay_roots() -> list[Path]:
    roots: list[Path] = []
    for accounts_root in iter_sc2_accounts_roots():
        if not accounts_root.exists():
            continue
        for replays_dir in accounts_root.rglob("Replays"):
            if replays_dir.is_dir():
                roots.append(replays_dir)
    return roots


def resolve_replay_upload_paths(
    configured_paths: list[str],
    local_handle: str | None = None,
) -> list[str]:
    """Paths for KS replay upload: configured > handle Multiplayer > all Multiplayer dirs."""
    roots: list[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        if not path.exists():
            return
        key = str(path.resolve())
        if key not in seen:
            seen.add(key)
            roots.append(path)

    for raw in configured_paths:
        add(Path(raw).expanduser())

    if local_handle:
        for path in find_replay_roots_for_handle(local_handle):
            add(path)

    if not roots:
        for path in discover_multiplayer_replay_dirs():
            add(path)

    if not roots:
        for path in default_replay_roots():
            add(path)

    return [str(path) for path in roots]


def iter_replay_files_under(root: Path) -> list[Path]:
    if root.is_file() and root.suffix.lower() == ".sc2replay":
        return [root]
    if not root.is_dir():
        return []
    files: list[Path] = []
    for path in root.rglob("*"):
        if path.suffix.lower() == ".sc2replay":
            files.append(path)
    return files
