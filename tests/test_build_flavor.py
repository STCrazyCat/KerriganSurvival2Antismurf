import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def test_generate_build_meta_memory_only(tmp_path: Path) -> None:
    import subprocess

    root = Path(__file__).resolve().parents[1]
    target = root / "src" / "antismurf" / "build_meta.py"
    backup = target.read_text(encoding="utf-8")
    try:
        subprocess.run(
            [sys.executable, str(root / "scripts" / "generate_build_meta.py")],
            check=True,
            cwd=root,
        )
        import antismurf.build_meta as bm

        importlib.reload(bm)
        assert bm.BUILD_FLAVOR == "memory"
        assert bm.MEMORY_SCAN_AVAILABLE is True
        assert bm.APP_EXE_BASENAME == "AntiSmurf"
        assert bm.INSTALLER_BASENAME == "AntiSmurf-Setup"
    finally:
        target.write_text(backup, encoding="utf-8")
        import antismurf.build_meta as bm2

        importlib.reload(bm2)


def test_memory_flavor_available_by_default() -> None:
    from antismurf.build_meta import BUILD_FLAVOR, MEMORY_SCAN_AVAILABLE
    from antismurf.features import memory_scan_available

    assert BUILD_FLAVOR == "memory"
    assert MEMORY_SCAN_AVAILABLE is True
    assert memory_scan_available() is True
