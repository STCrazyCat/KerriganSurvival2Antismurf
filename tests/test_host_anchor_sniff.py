import struct
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.lobby.memory_host_anchor import (
    DEFAULT_HOST_HANDLE_MODULE_OFFSET,
    SniffedHandleCandidate,
    confirm_host_handle_via_sniff,
    sniff_host_handle_storage,
)

MODULE_BASE = 0x1000000
RADIUS = 0x4000


def _fake_module():
    return type(
        "Mod", (), {"name": "SC2_x64.exe", "base": MODULE_BASE, "size": 0x8000000}
    )()


def _build_data() -> bytes:
    """锚点(在 span 中心)处放句柄 + struct 头 + profile_id 字段 + 名字;
    远处放一个无附近信息的干扰句柄。"""
    data = bytearray(2 * RADIUS + 0x4000)
    anchor_rel = RADIUS  # 锚点在读取窗口内的位置
    handle = b"5-S2-1-1234567"
    data[anchor_rel : anchor_rel + len(handle)] = handle
    struct.pack_into("<I", data, anchor_rel - 0x20 + 0x14, 0x5332)  # struct 头
    struct.pack_into("<I", data, anchor_rel + 0x40, 1234567)  # profile_id 字段
    data[anchor_rel + 0x50 : anchor_rel + 0x58] = b"HostName"
    far = anchor_rel + 0x3000
    data[far : far + 13] = b"5-S2-1-999999"  # 干扰:远处无证据句柄
    return bytes(data)


def test_sniff_finds_host_handle_with_nearby_evidence() -> None:
    data = _build_data()
    with mock.patch(
        "antismurf.lobby.memory_host_anchor._read_memory", return_value=data
    ):
        candidates = sniff_host_handle_storage(
            object(),
            [_fake_module()],
            anchor_offset=DEFAULT_HOST_HANDLE_MODULE_OFFSET,
            radius=RADIUS,
        )
    assert candidates, "应找到句柄候选"
    top = candidates[0]
    assert top.handle == "5-S2-1-1234567"
    assert top.nearby_profile_id == 1234567
    assert top.nearby_name == "HostName"
    assert top.struct_header_ok
    assert top.score >= 100.0


def test_sniff_candidate_without_nearby_info_scores_lower() -> None:
    data = _build_data()
    with mock.patch(
        "antismurf.lobby.memory_host_anchor._read_memory", return_value=data
    ):
        candidates = sniff_host_handle_storage(
            object(),
            [_fake_module()],
            anchor_offset=DEFAULT_HOST_HANDLE_MODULE_OFFSET,
            radius=RADIUS,
        )
    by_handle = {c.handle: c for c in candidates}
    assert "5-S2-1-1234567" in by_handle
    assert "5-S2-1-999999" in by_handle
    # 有证据的句柄分更高,排序靠前
    assert by_handle["5-S2-1-1234567"].score > by_handle["5-S2-1-999999"].score
    assert candidates[0].handle == "5-S2-1-1234567"


def test_confirm_returns_best_candidate() -> None:
    data = _build_data()
    with mock.patch(
        "antismurf.lobby.memory_host_anchor._read_memory", return_value=data
    ):
        cand = confirm_host_handle_via_sniff(
            object(),
            [_fake_module()],
            anchor_offset=DEFAULT_HOST_HANDLE_MODULE_OFFSET,
            radius=RADIUS,
            min_score=60.0,
        )
    assert cand is not None
    assert cand.handle == "5-S2-1-1234567"


def test_sniff_empty_module_returns_empty() -> None:
    with mock.patch(
        "antismurf.lobby.memory_host_anchor._read_memory", return_value=None
    ):
        candidates = sniff_host_handle_storage(
            object(),
            [_fake_module()],
            anchor_offset=DEFAULT_HOST_HANDLE_MODULE_OFFSET,
            radius=RADIUS,
        )
    assert candidates == []
