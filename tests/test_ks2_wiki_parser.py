import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from antismurf.community.response_parser import parse_ks2_wiki_rating


def test_parse_ks2_wiki_rating_core_max_and_playlike_average():
    mmr_data = {
        "cores": {"survivor": 2573, "kerrigan": 3181},
        "leaderboard_match": {"mmr": 3181},
    }
    playlike_data = {
        "games": [
            {"played_like": 2600.0},
            {"played_like": 2400.0},
        ]
    }
    mmr, playlike = parse_ks2_wiki_rating(mmr_data, playlike_data)
    assert mmr == 2573
    assert playlike == 2500


def test_parse_ks2_wiki_rating_leaderboard_fallback():
    mmr_data = {"leaderboard_match": {"mmr": 2991}}
    mmr, playlike = parse_ks2_wiki_rating(mmr_data, None)
    assert mmr == 2991
    assert playlike is None


def test_parse_ks2_wiki_rating_empty_games():
    mmr_data = {"cores": {"survivor": 2000, "kerrigan": 1800}}
    mmr, playlike = parse_ks2_wiki_rating(mmr_data, {"games": []})
    assert mmr == 1800
    assert playlike is None
