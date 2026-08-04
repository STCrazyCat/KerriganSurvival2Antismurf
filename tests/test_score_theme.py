from antismurf.app.score_theme import score_color
from antismurf.config.settings import AppConfig


def test_score_color_defaults() -> None:
    cfg = AppConfig()
    assert score_color(50.0, cfg) == "#ff5c5c"  # +分红色
    assert score_color(-20.0, cfg) == "#57d957"  # -分绿色
    assert score_color(0.0, cfg) == "#ffffff"  # 0 分白色


def test_score_color_custom() -> None:
    cfg = AppConfig(
        score_color_positive="#ff0000",
        score_color_negative="#00ff00",
        score_color_zero="#cccccc",
    )
    assert score_color(1.0, cfg) == "#ff0000"
    assert score_color(-1.0, cfg) == "#00ff00"
    assert score_color(0.0, cfg) == "#cccccc"
