"""
Offline test harness for utils/fb_analyzer.py

Run from the backend folder:
    python test_fb_analyzer.py

It uses fake "active cases" (plain dicts) and sample post text, so it needs NO
database, NO Facebook credentials, and works even before spaCy is installed
(falls back to regex-only location extraction). This is how you tune the
NAME_MATCH_THRESHOLD and eyeball location extraction before going live.
"""

from utils import fb_analyzer as fa

# Fake active cases (id + name is all best_name_match needs).
ACTIVE_CASES = [
    {"id": 1, "name": "Ahmed Sarim"},
    {"id": 2, "name": "Mohad Karim"},
    {"id": 3, "name": "Nadeem Ahmed"},
    {"id": 4, "name": "Steve Rogers"},
]

# Sample posts. Each tuple: (post, expected_match_id_or_None, note)
SAMPLE_POSTS = [
    (
        "URGENT! Please help. My brother Ahmed Sarim has been missing since "
        "Tuesday. He was last seen near Saddar, Karachi wearing a blue shirt.",
        1,
        "clean full-name match + trigger location",
    ),
    (
        "Missing person alert: NADEEM AHMED, age 24. Reported missing from "
        "Lahore. Contact family if seen.",
        3,
        "uppercase name + 'missing from' location",
    ),
    (
        "Have you seen Mohad? Full name Mohad Karim. Last spotted at "
        "Gulshan-e-Iqbal Block 5 two days ago.",
        2,
        "name split across sentence + 'last spotted at'",
    ),
    (
        "Found a lost dog near the park, very friendly. DM me.",
        None,
        "no person match -> should be ignored",
    ),
    (
        "Steve Rogers spotted in Brooklyn yesterday near the old gym.",
        4,
        "match + 'spotted in' location",
    ),
]


def main():
    print("=" * 70)
    print("fb_analyzer offline test")
    print("fuzzy backend :", fa._FUZZ_BACKEND)
    print("spaCy model   :", "loaded" if fa._get_nlp() is not None else "NOT installed (regex fallback)")
    print("name threshold:", fa.NAME_MATCH_THRESHOLD)
    print("=" * 70)

    passed = 0
    for i, (post, expected_id, note) in enumerate(SAMPLE_POSTS, 1):
        case, score = fa.best_name_match(post, ACTIVE_CASES)
        matched_id = case["id"] if (case and score >= fa.NAME_MATCH_THRESHOLD) else None
        location, conf = fa.extract_location(post)

        ok = matched_id == expected_id
        passed += ok
        print(f"\n[{i}] {note}")
        print(f"    post     : {post[:70]}...")
        print(f"    match    : {case['name'] if case else None} "
              f"(score={score:.1f} -> {'ACCEPT' if matched_id else 'reject'})")
        print(f"    location : {location!r} (conf={conf:.2f})")
        print(f"    expected : case_id={expected_id}  ->  {'PASS' if ok else 'FAIL'}")

    print("\n" + "=" * 70)
    print(f"name-match results: {passed}/{len(SAMPLE_POSTS)} as expected")
    print("=" * 70)


if __name__ == "__main__":
    main()
