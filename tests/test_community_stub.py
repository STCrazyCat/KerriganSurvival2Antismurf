import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.community.protocol import CommunityProvider
from antismurf.community.stub_store import StubCommunityStore
from antismurf.models.community import CommunityRating


@pytest.fixture
def stub_file(tmp_path: Path) -> Path:
    path = tmp_path / "community_stub.json"
    path.write_text(
        json.dumps(
            {
                "5-S2-1-19999": {"mmr": 5200, "mmr_playlike": 2800},
                "5-S2-1-1234": {"mmr": 3200, "mmr_playlike": 3100},
            }
        ),
        encoding="utf-8",
    )
    return path


def test_stub_implements_protocol(stub_file: Path) -> None:
    store = StubCommunityStore(stub_file)
    assert isinstance(store, CommunityProvider)


def test_submit_then_get_rating(stub_file: Path) -> None:
    async def run() -> None:
        store = StubCommunityStore(stub_file)
        request_id = await store.submit_handle("5-S2-1-19999")
        assert request_id

        rating = await store.get_rating_by_handle("5-S2-1-19999")
        assert rating.handle == "5-S2-1-19999"
        assert rating.mmr == 5200
        assert rating.mmr_playlike == 2800
        assert rating.request_id == request_id
        assert rating.has_data
        assert rating.analyzed_at is not None

    asyncio.run(run())


def test_fetch_rating_by_request_id(stub_file: Path) -> None:
    async def run() -> None:
        store = StubCommunityStore(stub_file)
        request_id = await store.submit_handle("5-S2-1-1234")

        rating = await store.fetch_rating(request_id)
        assert rating is not None
        assert rating.mmr == 3200
        assert rating.mmr_playlike == 3100

    asyncio.run(run())


def test_unknown_handle_returns_empty_rating(stub_file: Path) -> None:
    async def run() -> None:
        store = StubCommunityStore(stub_file)
        await store.submit_handle("5-S2-9-99999")

        rating = await store.get_rating_by_handle("5-S2-9-99999")
        assert rating.handle == "5-S2-9-99999"
        assert rating.mmr is None
        assert rating.mmr_playlike is None
        assert not rating.has_data

    asyncio.run(run())


def test_missing_stub_file_returns_empty_rating(tmp_path: Path) -> None:
    async def run() -> None:
        store = StubCommunityStore(tmp_path / "missing.json")
        rating = await store.get_rating_by_handle("5-S2-1-1")
        assert rating.handle == "5-S2-1-1"
        assert rating.mmr is None
        assert rating.mmr_playlike is None
        assert not rating.has_data

    asyncio.run(run())


def test_nested_payload_shape(tmp_path: Path) -> None:
    path = tmp_path / "nested.json"
    path.write_text(
        json.dumps({"5-S2-1-1": {"data": {"mmr": 4100, "mmrPlaylike": 3900}}}),
        encoding="utf-8",
    )

    async def run() -> None:
        store = StubCommunityStore(path)
        rating = await store.get_rating_by_handle("5-S2-1-1")
        assert rating.mmr == 4100
        assert rating.mmr_playlike == 3900

    asyncio.run(run())


def test_builtin_stub_json_has_sample_players() -> None:
    path = Path(__file__).resolve().parents[1] / "config" / "community_stub.json"
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "5-S2-1-19999" in data
    assert data["5-S2-1-19999"]["mmr"] == 5200
