"""
Scan service: glues the pure fb_analyzer pipeline to the database.

Used by both the admin route (routes/fb.py) and the standalone periodic runner
(fb_scan_runner.py). All functions assume an active Flask app context.

Auto-update policy (per the chosen design): when a post's name match scores >=
NAME_MATCH_THRESHOLD AND a location is extracted, the case's last_location is
overwritten immediately. EVERY processed match is recorded in FacebookSighting
(keeping previous_location) so any change is auditable and reversible.
"""

import time
from datetime import datetime
import itertools

from extensions import db
from models import MissingPerson, FacebookSighting
from utils import fb_analyzer as fa

# Locations used only to synthesize demo posts from existing cases.
_DEMO_LOCATIONS = ["Saddar, Karachi", "Lahore Cantt", "Gulshan-e-Iqbal, Karachi",
                   "Faisalabad", "Islamabad F-10", "Multan"]


def synthesize_demo_posts():
    """Build one fake post per active case so 'Scan Now' can be watched
    end-to-end before a real Facebook source is wired in."""
    cases = MissingPerson.query.filter_by(status='active').all()
    loc_cycle = itertools.cycle(_DEMO_LOCATIONS)
    posts = []
    for c in cases:
        loc = next(loc_cycle)
        posts.append({
            # unique id each run so the demo always re-applies (not deduped)
            "post_id": f"demo-{c.id}-{int(time.time()*1000)}",
            "text": f"URGENT missing person: {c.name} was last seen near {loc}. "
                    f"Please contact the family if you have any information.",
            "post_url": None,
        })
    return posts


def process_posts(posts):
    """Run the pipeline over an iterable of {post_id, text, post_url} dicts.

    Returns a summary dict: {scanned, matched, updated, skipped}.
    """
    active_cases = MissingPerson.query.filter_by(status='active').all()
    summary = {"scanned": 0, "matched": 0, "updated": 0, "skipped": 0, "results": []}

    for post in posts:
        summary["scanned"] += 1
        post_id = str(post.get("post_id")) if post.get("post_id") is not None else None
        text = post.get("text") or ""

        # Dedupe: skip posts we've already recorded.
        if post_id and FacebookSighting.query.filter_by(post_id=post_id).first():
            summary["skipped"] += 1
            continue

        case, score = fa.best_name_match(text, active_cases)
        if not case or score < fa.NAME_MATCH_THRESHOLD:
            continue  # no confident person match -> ignore post entirely
        summary["matched"] += 1

        location, conf = fa.extract_location(text)

        applied = False
        previous_location = case.last_location
        if location:
            # Auto-update last_location.
            case.last_location = location
            case.last_location_updated_at = datetime.utcnow()
            case.last_location_source = 'facebook'
            applied = True
            summary["updated"] += 1

        # Per-post detail so the UI can show exactly what was extracted.
        summary["results"].append({
            "person_name": case.name,
            "match_score": round(score, 1),
            "previous_location": previous_location,
            "new_location": location,
            "applied": applied,
        })

        sighting = FacebookSighting(
            missing_person_id=case.id,
            post_id=post_id,
            post_url=post.get("post_url"),
            post_text=text,
            matched_name=case.name,
            match_score=round(score, 1),
            previous_location=previous_location,
            new_location=location,
            applied=applied,
        )
        db.session.add(sighting)

    db.session.commit()
    return summary


def scrape_posts(config):
    """Pull posts from the configured Facebook source (stub by default)."""
    return fa.fetch_posts(
        group=config.get("FB_GROUP"),
        pages=config.get("FB_PAGES", 2),
        cookies=config.get("FB_COOKIES"),
    )


def run_scan(config, posts=None, demo=False):
    """Entry point. Choose the post source, then process.

    - demo=True            -> synthesize posts from active cases (watch the flow)
    - posts=[...]          -> process the supplied posts (e.g. manual/test)
    - otherwise            -> scrape the configured Facebook source
    """
    if demo:
        posts = synthesize_demo_posts()
    elif posts is None:
        posts = scrape_posts(config)
    return process_posts(posts)
