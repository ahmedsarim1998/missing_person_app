"""
Facebook post analyzer for the Missing Person App.

This module is intentionally split into PURE functions (no Flask / no DB) so the
matching + location-extraction logic can be unit-tested offline against sample
post text, before any live Facebook scraping is wired in.

Pipeline (per post):
    text --> extract_location() --> (location, confidence)
    text --> best_name_match(active_cases) --> (case, score)
    if score >= NAME_MATCH_THRESHOLD and location: -> caller updates last_location

The only Facebook-specific code is fetch_posts(), which is stubbed by default so
the rest of the pipeline runs with zero external dependencies.
"""

import re

# ---------------------------------------------------------------------------
# Tunable thresholds
# ---------------------------------------------------------------------------
NAME_MATCH_THRESHOLD = 88.0   # fuzzy score (0-100) required to consider it the same person
MIN_LOCATION_LEN = 2          # ignore junk single-char "locations"


# ---------------------------------------------------------------------------
# Fuzzy name matching (rapidfuzz preferred, difflib fallback)
# ---------------------------------------------------------------------------
try:
    from rapidfuzz import fuzz as _fuzz

    def _name_score(name, text):
        # partial_token_sort_ratio handles word reordering AND finds the name
        # as a substring inside a longer post.
        return float(_fuzz.partial_token_sort_ratio(name.lower(), text.lower()))

    _FUZZ_BACKEND = "rapidfuzz"
except ImportError:
    from difflib import SequenceMatcher

    def _name_score(name, text):
        # Fallback: slide the name across the text and keep the best window score.
        name = name.lower().strip()
        text = text.lower()
        if not name:
            return 0.0
        n = len(name)
        if n >= len(text):
            return SequenceMatcher(None, name, text).ratio() * 100.0
        best = 0.0
        # step in reasonable increments to keep it cheap on long posts
        for i in range(0, len(text) - n + 1, max(1, n // 4)):
            window = text[i:i + n]
            r = SequenceMatcher(None, name, window).ratio()
            if r > best:
                best = r
        return best * 100.0

    _FUZZ_BACKEND = "difflib"


def best_name_match(text, candidates):
    """Return (best_candidate, score) for the highest-scoring active case.

    candidates: iterable of objects/dicts exposing `id` and `name`.
                Works with SQLAlchemy MissingPerson rows or plain dicts (tests).
    Returns (None, 0.0) if nothing scores at all.
    """
    best_candidate = None
    best_score = 0.0
    for cand in candidates:
        name = cand["name"] if isinstance(cand, dict) else cand.name
        if not name:
            continue
        score = _name_score(name, text)
        if score > best_score:
            best_score = score
            best_candidate = cand
    return best_candidate, best_score


# ---------------------------------------------------------------------------
# Location extraction
# ---------------------------------------------------------------------------
# Real missing-person posts come in many shapes: free-form sentences ("...was
# last seen near Gulshan..."), and structured/labelled forms ("Last seen: near
# bufferzone Karachi", "Location - Clifton Block 5"). The extractor below handles
# both, tolerates any separator (space/colon/dash/comma) after the trigger, and
# does NOT require the place to be Capitalised (so "bufferzone karachi" works).

# Strong phrases that introduce a last-seen location. Ordered longest-first so
# the most specific alternative wins at a given position.
_PHRASE_TRIGGER = re.compile(
    r"\b(?:"
    r"last\s*known\s*location|last\s*seen\s*(?:at|near|in|around)?|"
    r"last\s*location|went\s*missing\s*(?:from|near|at)|"
    r"missing\s*(?:from|near|at)|disappeared\s*(?:from|near|at)|"
    r"spotted\s*(?:at|near|in|around)?|seen\s*(?:at|near|in|around)|"
    r"reported\s*(?:from|near|at)"
    r")"
    r"\s*[:\-–—,]?\s*"                       # optional separator
    r"(?:at|near|in|from|around|close\s+to)?\s*",      # optional preposition
    re.IGNORECASE,
)

# Labelled fields ("Location: X", "Area - Y"). These generic words are only
# treated as a location cue when followed by an explicit ':' or '-' separator,
# to avoid false positives on the bare word in a sentence.
_LABEL_TRIGGER = re.compile(
    r"\b(?:location|address|area|place|last\s*location|last\s*known\s*location)"
    r"\s*[:\-–—]\s*"
    r"(?:at|near|in|from|around|close\s+to)?\s*",
    re.IGNORECASE,
)

# Once we're reading a location, these words signal it has ended (contact info,
# physical description, etc.). Kept conservative so real place names survive.
_STOP = re.compile(
    r"\b(?:please|kindly|pls|contact|call|inform|informed|information|"
    r"if\s+you|whats?app|phone|mobile|cell|helpline|reward|"
    r"age|father|mother|son|daughter|brother|sister|wearing|wore|"
    r"height|complexion|cnic|nic|dob|since|reward|"
    # time expressions that often trail the place
    r"last\s+night|yesterday|today|tonight|tomorrow|"
    r"this\s+(?:morning|afternoon|evening|night)|"
    r"morning|afternoon|evening|night|noon|ago)\b",
    re.IGNORECASE,
)

# A trailing clock time ("around 5pm", "at 10:30"). Requires a time word (am/pm)
# or a preceding around/at/about + number, so it never trims "Block 5"/"Phase 6".
_TRAIL_TIME = re.compile(
    r"\s+(?:(?:around|at|about)\s+\d.*|\d{1,2}(?:[:.]\d{2})?\s*[ap]\.?m\.?.*)$",
    re.IGNORECASE,
)

# Lazily-loaded spaCy model (optional). If unavailable we fall back to regex only.
_NLP = None
_NLP_TRIED = False


def _get_nlp():
    global _NLP, _NLP_TRIED
    if _NLP_TRIED:
        return _NLP
    _NLP_TRIED = True
    try:
        import spacy
        _NLP = spacy.load("en_core_web_sm")
    except Exception:
        _NLP = None  # regex-only fallback
    return _NLP


def _clean_location(loc):
    if not loc:
        return None
    # Trim the span at the first line break or sentence end, then at any stop
    # word (contact info / description that often follows the place).
    loc = re.split(r"[\r\n]", loc, 1)[0]
    loc = re.split(r"[.!?](?:\s|$)", loc, 1)[0]
    stop = _STOP.search(loc)
    if stop:
        loc = loc[:stop.start()]
    loc = _TRAIL_TIME.sub("", loc)   # strip a trailing clock time
    # Drop a leading preposition that slipped through ("near X" -> "X").
    loc = re.sub(r"^\s*(?:at|near|in|from|around|close\s+to)\s+", "", loc,
                 flags=re.IGNORECASE)
    loc = loc.strip(" \t\r\n.,:;-–—")
    loc = re.sub(r"\s+", " ", loc)
    # Locations are short; keep at most 6 words to avoid trailing sentence junk.
    words = loc.split()
    if len(words) > 6:
        loc = " ".join(words[:6])
    loc = loc.strip(" \t\r\n.,:;-–—")
    if len(loc) < MIN_LOCATION_LEN:
        return None
    if not re.search(r"[A-Za-z]", loc):   # must contain a letter
        return None
    return loc


def _regex_candidates(text):
    """All location candidates from phrase + labelled triggers, best-first
    (most words, then longest)."""
    cands = []  # (word_count, length, location)
    for trigger in (_PHRASE_TRIGGER, _LABEL_TRIGGER):
        for m in trigger.finditer(text):
            loc = _clean_location(text[m.end(): m.end() + 120])
            if loc:
                cands.append((len(loc.split()), len(loc), loc))
    cands.sort(reverse=True)
    # de-dupe while preserving order
    seen, ordered = set(), []
    for _, _, loc in cands:
        key = loc.lower()
        if key not in seen:
            seen.add(key)
            ordered.append(loc)
    return ordered


def extract_location(text):
    """Return (location_str_or_None, confidence_0_to_1).

    Strategy:
      1. Find a trigger phrase or labelled field and read the location after it,
         trimming at line/sentence ends and contact-info stop-words.
      2. If spaCy is available, refine to a real GPE/LOC entity within the
         candidate (raises confidence); otherwise use the regex span directly.
    """
    if not text:
        return None, 0.0

    candidates = _regex_candidates(text)
    best = candidates[0] if candidates else None

    nlp = _get_nlp()
    if nlp is not None and best is not None:
        # Prefer a named place entity found inside the regex candidate.
        doc = nlp(best)
        geos = [e.text for e in doc.ents if e.label_ in ("GPE", "LOC", "FAC")]
        if geos:
            refined = _clean_location(", ".join(geos))
            if refined:
                return refined, 0.9

    if best:
        return best, 0.7

    # No trigger matched — last resort: a spaCy place entity anywhere in the text.
    if nlp is not None:
        doc = nlp(text)
        for e in doc.ents:
            if e.label_ in ("GPE", "LOC", "FAC"):
                loc = _clean_location(e.text)
                if loc:
                    return loc, 0.5

    return None, 0.0


# ---------------------------------------------------------------------------
# Facebook ingestion (the ONLY FB-specific code) -- stubbed by default
# ---------------------------------------------------------------------------
# Hard cap on posts pulled per scan, so a live run can't loop indefinitely
# (each post is a network round-trip and Facebook throttles aggressively).
_MAX_POSTS_PER_SCAN = 60


def fetch_posts(group, pages=2, cookies=None, _sample=None):
    """Yield dicts: {"post_id", "text", "post_url"}.

    Live mode uses `facebook-scraper` to pull recent posts from a Facebook group.
    Group posts require an authenticated session, so `cookies` must be the path
    to a Netscape-format cookies.txt exported from a logged-in browser (on the
    deployed app, put it on the persistent volume, e.g. /data/cookies.txt, and
    set FB_COOKIES to that path).

    Passing `_sample` bypasses Facebook entirely and yields the given posts —
    used by the offline unit tests so the rest of the pipeline stays testable
    with zero external dependencies.
    """
    if _sample is not None:
        for p in _sample:
            yield p
        return

    if not group:
        raise RuntimeError(
            "FB_GROUP is not configured. Set it to your Facebook group id "
            "(or name) in the environment before running a live scan."
        )

    try:
        from facebook_scraper import get_posts
    except ImportError as exc:  # optional dep, not in every environment
        raise RuntimeError(
            "facebook-scraper is not installed in this environment, so live "
            "group scanning is unavailable. Add it to requirements and redeploy."
        ) from exc

    # Resolve the cookies file. Groups are private-ish; without a valid session
    # Facebook returns nothing (or blocks), so a real, existing file is required.
    cookies_arg = None
    if cookies:
        import os
        if os.path.isfile(cookies):
            cookies_arg = cookies
        else:
            raise RuntimeError(
                "FB_COOKIES is set to '%s' but no such file exists. Point it at "
                "a Netscape-format cookies.txt (e.g. /data/cookies.txt)." % cookies
            )

    count = 0
    for post in get_posts(group=group, pages=pages, cookies=cookies_arg,
                          options={"comments": False, "reactors": False}):
        yield {
            "post_id": (str(post.get("post_id"))
                        if post.get("post_id") is not None else None),
            "text": post.get("text") or "",
            "post_url": post.get("post_url"),
        }
        count += 1
        if count >= _MAX_POSTS_PER_SCAN:
            break
