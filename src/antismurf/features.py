from __future__ import annotations

from antismurf.build_meta import MEMORY_SCAN_AVAILABLE


def memory_scan_available() -> bool:
    return MEMORY_SCAN_AVAILABLE
