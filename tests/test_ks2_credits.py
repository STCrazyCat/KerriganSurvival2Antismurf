import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.community.ks2_credits import Ks2CreditsInfo, fetch_ks2_credits


def test_fetch_ks2_credits_parses_response(monkeypatch) -> None:
    class FakeResponse:
        status_code = 200
        headers = {"content-type": "application/json"}

        @staticmethod
        def json():
            return {
                "replays": 42,
                "code": "123/token",
                "penalty": 2,
                "updated": 1000.5,
            }

        def raise_for_status(self) -> None:
            return None

    captured: dict = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured["params"] = kwargs.get("params")
        return FakeResponse()

    import httpx

    monkeypatch.setattr(httpx, "get", fake_get)
    info = fetch_ks2_credits("5-S2-1-6738824")
    assert captured["url"].endswith("/api/credits")
    assert captured["params"] == {"player_handle": "5-S2-1-6738824"}
    assert info == Ks2CreditsInfo(
        handle="5-S2-1-6738824",
        replay_credits=42,
        redemption_code="123/token",
        penalty=2,
        updated=1000.5,
    )
    assert info.net_credits == 40


def test_fetch_ks2_credits_requires_handle() -> None:
    try:
        fetch_ks2_credits("")
    except ValueError as exc:
        assert "handle" in str(exc).lower()
    else:
        raise AssertionError("expected ValueError")
