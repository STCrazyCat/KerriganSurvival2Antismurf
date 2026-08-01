import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.vision.map_detector import best_map_match, is_target_map


def test_is_target_map_chinese() -> None:
    targets = ["凯瑞甘生存2", "Kerrigan Survival 2"]
    assert is_target_map("凯瑞甘生存2", targets)
    assert is_target_map(" 凯瑞甘生存2 v123 ", targets)


def test_is_target_map_english() -> None:
    targets = ["凯瑞甘生存2", "Kerrigan Survival 2"]
    assert is_target_map("Kerrigan Survival 2", targets)


def test_best_map_match_partial_ocr() -> None:
    targets = ["凯瑞甘生存2", "Kerrigan Survival 2"]
    assert best_map_match("凯瑞甘生存2地图", targets) == "凯瑞甘生存2"
