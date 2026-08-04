"""Score display theming: configurable colors per score sign.

Defaults: positive (suspicion) = red, negative (trust) = green, zero = white.
Colors are stored in AppConfig and editable in the settings dialog.
"""

from __future__ import annotations

from antismurf.config.settings import AppConfig

DEFAULT_POSITIVE = "#ff5c5c"
DEFAULT_NEGATIVE = "#57d957"
DEFAULT_ZERO = "#ffffff"


def score_color(score: float, config: AppConfig) -> str:
    """Return the configured color for a score value."""
    if score > 0:
        return config.score_color_positive
    if score < 0:
        return config.score_color_negative
    return config.score_color_zero
