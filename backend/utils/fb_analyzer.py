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
# Phrases that typically precede a last-seen location in a missing-person post.
_LOCATION_TRIGGERS = re.compile(
    r"(?:last\s+seen|last\s+spotted|spotted|seen|missing\s+from|"
    r"went\s+missing\s+(?:from|near|at)|disappeared\s+(?:from|near|at)|"
    r"reported\s+(?:from|near|at))\s+"
    r"(?:at|near|in|from|around)?\s*",
    re.IGNORECASE,
)

# After a trigger, grab a location-looking span: capitalized words joined by
# spaces/commas. A '.' is NOT part of a token, so the span stops at a sentence
# boundary (e.g. "Lahore. Contact" -> "Lahore").
_LOCATION_SPAN = re.compile(
    r"([A-Z][\w&'-]*(?:[ ,]+(?:[A-Z][\w&'-]*|the|of|and|near))*)"
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
    loc = loc.strip(" .,:;-\n\t")
    # collapse internal whitespace
    loc = re.sub(r"\s+", " ", loc)
    if len(loc) < MIN_LOCATION_LEN:
        return None
    return loc


def extract_location(text):
    """Return (location_str_or_None, confidence_0_to_1).

    Strategy:
      1. Find a trigger phrase ("last seen near ...") and read the span after it.
      2. If spaCy is available, refine using GPE/LOC named entities (prefer one
         that appears after the trigger). spaCy presence raises confidence.
    """
    if not text:
        return None, 0.0

    # A post can contain several trigger words ("...you seen X? ...spotted at Y").
    # Collect a candidate location after each, then prefer the most place-like
    # one (more words first, then longer) rather than just the first hit.
    trigger_loc = None
    trigger_pos = None
    candidates = []  # (word_count, length, location, position)
    for m in _LOCATION_TRIGGERS.finditer(text):
        pos = m.end()
        tail = text[pos: pos + 80]
        span = _LOCATION_SPAN.search(tail)
        if not span:
            continue
        loc = _clean_location(span.group(1))
        if loc:
            candidates.append((len(loc.split()), len(loc), loc, pos))
    if candidates:
        candidates.sort(reverse=True)  # most words, then longest
        _, _, trigger_loc, trigger_pos = candidates[0]

    nlp = _get_nlp()
    if nlp is not None:
        doc = nlp(text)
        geos = [ent for ent in doc.ents if ent.label_ in ("GPE", "LOC", "FAC")]
        if geos:
            chosen = None
            if trigger_pos is not None:
                # prefer the first geo entity that starts at/after the trigger
                after = [e for e in geos if e.start_char >= trigger_pos]
                chosen = after[0] if after else geos[0]
            else:
                chosen = geos[0]
            loc = _clean_location(chosen.text)
            if loc:
                # spaCy-confirmed location: high confidence, higher if a trigger
                # phrase also pointed here.
                conf = 0.9 if trigger_loc else 0.7
                return loc, conf

    if trigger_loc:
        # regex-only hit (no spaCy or spaCy found nothing): medium confidence
        return trigger_loc, 0.6

    return None, 0.0


# ---------------------------------------------------------------------------
# Facebook ingestion (the ONLY FB-specific code) -- stubbed by default
# ---------------------------------------------------------------------------
def fetch_posts(group, pages=2, cookies=None, _sample=None):
    """Yield dicts: {"post_id", "text", "post_url"}.

    By default this is a stub that yields nothing (or `_sample` if provided),
    so the rest of the pipeline is fully testable offline. Swap the body for
    facebook_scraper.get_posts(...) when you're ready to go live:

        from facebook_scraper import get_posts
        for post in get_posts(group, pages=pages, cookies=cookies,
                              options={"comments": False}):
            yield {
                "post_id": str(post.get("post_id")),
                "text": post.get("text") or "",
                "post_url": post.get("post_url"),
            }
    """
    if _sample is not None:
        for p in _sample:
            yield p
    # else: stub -> nothing. Live implementation goes here (see docstring).
    return
