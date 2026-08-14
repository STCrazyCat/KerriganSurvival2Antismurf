import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.app.gui import suspect_name_color_for
from antismurf.config.settings import AppConfig, HandleMarkRule, HandleTrustRule
from antismurf.models.evaluation import PlayerRecord


def _record(handle: str, tier: str = "low", whitelisted: bool = False) -> PlayerRecord:
    return PlayerRecord(
        handle=handle,
        slot_index=0,
        discriminator=1,
        tier=tier,
        score=50,
        whitelisted=whitelisted,
    )


def test_high_tier_name_gets_suspect_color() -> None:
    cfg = AppConfig()
    assert suspect_name_color_for(_record("5-S2-1-1", tier="high"), cfg) == "#ff5c5c"
    assert (
        suspect_name_color_for(_record("5-S2-1-1", tier="critical"), cfg) == "#ff5c5c"
    )
    assert suspect_name_color_for(_record("5-S2-1-1", tier="low"), cfg) is None


def test_marked_handle_gets_suspect_color() -> None:
    cfg = AppConfig()
    cfg.handle_mark_rules = [HandleMarkRule(handle="5-S2-1-777", weight=200)]
    assert (
        suspect_name_color_for(_record("5-S2-1-777", tier="low"), cfg) == "#ff5c5c"
    )
    assert suspect_name_color_for(_record("5-S2-1-888", tier="low"), cfg) is None


def test_blocklisted_gets_suspect_color() -> None:
    cfg = AppConfig()
    cfg.blocklist_handles = {"5-S2-1-666"}
    assert (
        suspect_name_color_for(_record("5-S2-1-666", tier="low"), cfg) == "#ff5c5c"
    )
    assert suspect_name_color_for(_record("5-S2-1-888", tier="low"), cfg) is None


def test_non_whitelisted_in_whitelist_mode() -> None:
    cfg = AppConfig()
    cfg.whitelist_mode = True
    assert (
        suspect_name_color_for(_record("5-S2-1-2", whitelisted=False), cfg)
        == "#ff5c5c"
    )
    assert suspect_name_color_for(_record("5-S2-1-2", whitelisted=True), cfg) is None


def test_trusted_not_colored_in_whitelist_mode() -> None:
    cfg = AppConfig()
    cfg.whitelist_mode = True
    cfg.handle_trust_rules = [HandleTrustRule(handle="5-S2-1-9", weight=-20)]
    assert suspect_name_color_for(_record("5-S2-1-9"), cfg) is None


def test_no_suspect_in_default_mode() -> None:
    cfg = AppConfig()
    assert suspect_name_color_for(_record("5-S2-1-4"), cfg) is None


def test_custom_suspect_color() -> None:
    cfg = AppConfig(suspect_name_color="#ffaa00")
    assert suspect_name_color_for(_record("5-S2-1-1", tier="high"), cfg) == "#ffaa00"
