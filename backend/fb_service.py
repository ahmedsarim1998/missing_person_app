"""
Scan service: glues the pure fb_analyzer pipeline to the database.

Used by both the admin route (routes/fb.py) and the standalone periodic runner
(fb_scan_runner.py). All functions assume an active Flask app context.

Auto-update policy (per the chosen design): when a post's name match scores >=
NAME_MATCH_THRESHOLD AND a location is extracted, the case's last_location is
overwritten immediately. EVERY processed match is recorded in FacebookSighting
(keeping previous_location) so any change is auditable and reversible.
"""

import os
import time
from datetime import datetime
import itertools

from werkzeug.utils import secure_filename

from extensions import db
from models import MissingPerson, FacebookSighting
from utils import fb_analyzer as fa
from notify_service import notify_case_update

_ALLOWED_IMG = {"png", "jpg", "jpeg", "webp"}

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
            notify_case_update(
                case, "New sighting: %s spotted near %s" % (case.name, location),
                "%s may have been spotted near %s (from a social-media post). "
                "Open their case page to review and confirm." % (case.name, location))

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


def _save_sighting_images(files, upload_folder):
    """Save uploaded post images to <upload_folder>/sightings and decode them.

    Returns a list of (public_url, bgr_image) tuples. Invalid/undecodable files
    are skipped. bgr_image is kept so the caller can run face matching without
    re-reading from disk.
    """
    import cv2
    import numpy as np

    out = []
    sdir = os.path.join(upload_folder, "sightings")
    os.makedirs(sdir, exist_ok=True)
    for f in files or []:
        if not f or not getattr(f, "filename", ""):
            continue
        ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
        if ext not in _ALLOWED_IMG:
            continue
        data = f.read()
        if not data:
            continue
        bgr = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if bgr is None:
            continue
        fname = "sight_%d_%s" % (int(time.time() * 1000), secure_filename(f.filename))
        with open(os.path.join(sdir, fname), "wb") as fh:
            fh.write(data)
        out.append(("/static/uploads/sightings/%s" % fname, bgr))
    return out


def _embedding_from_bgr(bgr_image):
    """Best face embedding from a BGR image, or None if no face is found."""
    import cv2
    from utils.face_recognition import FaceModel
    model = FaceModel.get_instance()
    rgb = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2RGB)
    dets = model.detect_faces(rgb)
    if not dets:
        return None
    best = max(dets, key=lambda d: d["box"][2] * d["box"][3])
    face = model.extract_face(rgb, best["box"])
    if face.size == 0:
        return None
    return model.get_embedding(face)


def _match_faces_in_image(bgr_image, active_cases, threshold):
    """Detect faces in a BGR image and match each against active-case embeddings.

    Returns a list of {name, distance, matched} — one entry per detected face
    that could be compared. Reuses the same FaceNet pipeline as case creation
    and the live stream.
    """
    import cv2
    from utils.face_recognition import FaceModel

    model = FaceModel.get_instance()
    rgb = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2RGB)
    results = []
    for det in model.detect_faces(rgb):
        face = model.extract_face(rgb, det["box"])
        if face.size == 0:
            continue
        emb = model.get_embedding(face)
        best_name, best_dist = None, float("inf")
        for c in active_cases:
            if not c.embedding_blob:
                continue
            for db_emb in c.embedding_blob:
                d = model.distance(emb, db_emb)
                if d < best_dist:
                    best_dist, best_name = d, c.name
        if best_name is not None:
            results.append({
                "name": best_name,
                "distance": round(float(best_dist), 3),
                "matched": bool(best_dist < threshold),
            })
    return results


def _summarize_faces(face_results):
    """One-line verdict for storage/display."""
    if not face_results:
        return None
    matches = [f for f in face_results if f.get("matched")]
    if matches:
        best = min(matches, key=lambda f: f["distance"])
        return "Face match: %s" % best["name"]
    return "No face match among active cases"


def _create_case_from_post(text, location, saved_images, reporter):
    """Open a new active case from a post that matched no existing case.

    Needs a readable name and at least one detectable face. Returns a summary
    dict (with a 'reason' explaining any failure so the UI can guide the admin).
    """
    name = fa.extract_name(text)
    if not name:
        return {"created": False, "reason": "Couldn't read a name — add a 'Name: ...' line to open a case."}
    if not saved_images:
        return {"created": False, "reason": "Attach at least one clear photo to open a new case."}

    embeddings = []
    for _url, bgr in saved_images:
        try:
            emb = _embedding_from_bgr(bgr)
        except Exception:
            emb = None
        if emb is not None:
            embeddings.append(emb)
    if not embeddings:
        return {"created": False, "reason": "No face detected in the attached photo(s)."}

    new = MissingPerson(
        name=name,
        last_location=location,
        status="active",
        photo_path=saved_images[0][0],
        embedding_blob=embeddings,
        last_location_updated_at=datetime.utcnow() if location else None,
        last_location_source="facebook" if location else None,
        reporter=reporter,
    )
    db.session.add(new)
    db.session.commit()
    return {"created": True, "id": new.id, "name": name, "location": location}


def analyze_manual_post(text, image_files, upload_folder, match_threshold,
                        create_if_missing=False, reporter=None):
    """Analyze one manually-pasted post plus optional attached images.

    Runs the same name-match + location-extraction as the scanner, saves any
    attached images to the persistent uploads volume, runs face recognition on
    them against active cases, records a FacebookSighting, and returns a rich
    result dict for the UI. Face matching degrades gracefully: if the model or
    embeddings are unavailable, the text + image attachment still succeed.

    If `create_if_missing` and no active case matches, a new case is created
    from the post's name + attached face photo(s) (this is the "someone reported
    a person who isn't on the site yet -> open a case for them" flow).
    """
    text = (text or "").strip()
    active_cases = MissingPerson.query.filter_by(status="active").all()

    case, score = fa.best_name_match(text, active_cases) if text else (None, 0.0)
    matched = bool(case and score >= fa.NAME_MATCH_THRESHOLD)
    location, _conf = fa.extract_location(text) if text else (None, 0.0)

    # Save + face-check attached images (best-effort).
    saved = _save_sighting_images(image_files, upload_folder)
    image_urls = [url for url, _bgr in saved]
    face_results = []
    if saved:
        try:
            for url, bgr in saved:
                for fr in _match_faces_in_image(bgr, active_cases, match_threshold):
                    fr["image"] = url
                    face_results.append(fr)
        except Exception:
            face_results = []  # model unavailable -> keep text + images only

    result = {
        "matched": matched,
        "person_name": case.name if matched else None,
        "match_score": round(score, 1) if case else 0.0,
        "previous_location": None,
        "new_location": None,
        "applied": False,
        "images": image_urls,
        "face_results": face_results,
        "face_summary": _summarize_faces(face_results),
        "created_case": None,
    }

    if not matched:
        # No existing case. Optionally open a new one from the post.
        if create_if_missing:
            result["created_case"] = _create_case_from_post(text, location, saved, reporter)
        return result

    previous_location = case.last_location
    applied = False
    if location:
        case.last_location = location
        case.last_location_updated_at = datetime.utcnow()
        case.last_location_source = "facebook"
        applied = True
        notify_case_update(
            case, "New sighting: %s spotted near %s" % (case.name, location),
            "%s may have been spotted near %s (from a social-media post). "
            "Open their case page to review and confirm." % (case.name, location))

    result["previous_location"] = previous_location
    result["new_location"] = location
    result["applied"] = applied

    db.session.add(FacebookSighting(
        missing_person_id=case.id,
        post_id="manual-%d" % int(time.time() * 1000),
        post_url=None,
        post_text=text,
        matched_name=case.name,
        match_score=round(score, 1),
        previous_location=previous_location,
        new_location=location,
        applied=applied,
        image_paths=",".join(image_urls) if image_urls else None,
        face_match=result["face_summary"],
    ))
    db.session.commit()
    return result


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
