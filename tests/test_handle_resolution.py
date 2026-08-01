import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.config.settings import AppConfig
from antismurf.scoring.expression_engine import RuleContext, resolve_variable
from antismurf.vision.handle_resolution import resolve_handle_detailed
from antismurf.vision.lobby_text_parser import (
    digit_obfuscation_suspected,
    parse_lobby_identity,
)


def test_digit_obfuscation_detects_l_in_id() -> None:
    assert digit_obfuscation_suspected("#673882l")
    identity = parse_lobby_identity("#673882l")
    assert identity is not None
    assert identity.digit_obfuscation
    assert identity.profile_id == 6738821


def test_resolve_handle_constructs_from_host_region() -> None:
    config = AppConfig(host_handle="5-S2-1-12208616")
    identity = parse_lobby_identity("#6738824")
    assert identity is not None
    result = resolve_handle_detailed(identity, config)
    assert result.resolved
    assert result.constructed
    assert result.handle == "5-S2-1-6738824"


def test_rule_variables_for_handle_quality() -> None:
    ctx = RuleContext(
        handle="5-S2-1-1",
        profile_id=1,
        profile=None,
        handle_resolved=True,
        handle_ambiguous=True,
        handle_candidate_count=2,
        handle_constructed=False,
        handle_from_binding=True,
        ocr_digit_obfuscation=True,
    )
    assert resolve_variable("handle.ambiguous", ctx) is True
    assert resolve_variable("handle.candidate_count", ctx) == 2
    assert resolve_variable("ocr.digit_obfuscation", ctx) is True
    assert resolve_variable("handle.from_binding", ctx) is True
