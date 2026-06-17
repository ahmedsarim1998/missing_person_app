"""Social-media analyzer: fuzzy name matching + location extraction (offline)."""
from utils import fb_analyzer as fa

ACTIVE_CASES = [
    {"id": 1, "name": "Ahmed Sarim"},
    {"id": 2, "name": "Steve Rogers"},
    {"id": 3, "name": "Nadeem Ahmed"},
]


def test_name_match_above_threshold():
    text = ("URGENT! My brother Ahmed Sarim has been missing since Tuesday. "
            "He was last seen near Saddar, Karachi.")
    case, score = fa.best_name_match(text, ACTIVE_CASES)
    assert case["id"] == 1
    assert score >= fa.NAME_MATCH_THRESHOLD


def test_no_match_for_unrelated_post():
    text = "Beautiful weather in the northern mountains this weekend."
    case, score = fa.best_name_match(text, ACTIVE_CASES)
    assert score < fa.NAME_MATCH_THRESHOLD


def test_location_extraction():
    loc, conf = fa.extract_location("He was last seen near Saddar, Karachi wearing blue.")
    assert loc is not None
    assert "Saddar" in loc or "Karachi" in loc
    assert 0.0 < conf <= 1.0


def test_location_absent():
    loc, conf = fa.extract_location("Please share this post to help find him.")
    assert loc is None
    assert conf == 0.0
