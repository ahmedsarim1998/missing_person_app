import re
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
from extensions import db
from models import MissingPerson, FacebookSighting, MatchAlert
from werkzeug.utils import secure_filename
import os
import cv2
from utils.face_recognition import FaceModel
from security import login_required, admin_required
from flask_jwt_extended import get_jwt_identity, get_jwt
from logging_config import audit_logger

cases_bp = Blueprint('cases', __name__)


def _allowed(filename):
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    return ext in current_app.config['ALLOWED_IMAGE_EXTENSIONS']


@cases_bp.route('/', methods=['GET'])
def get_cases():
    cases = MissingPerson.query.order_by(MissingPerson.created_at.desc()).all()
    result = []
    for c in cases:
        result.append({
            "id": c.id,
            "name": c.name,
            "national_id": c.national_id,
            "last_location": c.last_location,
            "status": c.status,
            "photo_path": c.photo_path
        })
    return jsonify(result), 200

MIN_PHOTOS = 1
MAX_PHOTOS = 10


def process_case_photos(files, name):
    """Save 1–10 photos for `name`, computing a face embedding for each.

    Returns (main_photo_url, embeddings, error_message). On any validation
    problem error_message is set and the first two are None.
    """
    valid = [f for f in files if f and f.filename]
    if len(valid) < MIN_PHOTOS:
        return None, None, f"Please upload at least {MIN_PHOTOS} photo."
    if len(valid) > MAX_PHOTOS:
        return None, None, f"Please upload at most {MAX_PHOTOS} photos (you sent {len(valid)})."

    person_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], secure_filename(name))
    os.makedirs(person_dir, exist_ok=True)

    model = FaceModel.get_instance()
    embeddings, main_photo = [], None
    for file in valid:
        if not _allowed(file.filename):
            return None, None, f"Unsupported file type: {file.filename}"
        filename = secure_filename(file.filename)
        path = os.path.join(person_dir, filename)
        file.save(path)
        url = f"/static/uploads/{secure_filename(name)}/{filename}"
        if main_photo is None:
            main_photo = url   # first valid photo is the display photo

        img = cv2.imread(path)
        if img is None:
            continue
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        detections = model.detect_faces(rgb)
        if detections:
            best = max(detections, key=lambda d: d['box'][2] * d['box'][3])
            embeddings.append(model.get_embedding(model.extract_face(rgb, best['box'])))

    if not embeddings:
        return None, None, "No faces detected in the uploaded photos. Use clear, front-facing photos."
    return main_photo, embeddings, None


@cases_bp.route('/', methods=['POST'])
@login_required
def create_case():
    if 'photos' not in request.files:
        return jsonify({"msg": "No photos"}), 400

    files = request.files.getlist('photos')
    name = (request.form.get('name') or '').strip()
    national_id = (request.form.get('national_id') or '').strip()
    last_location = (request.form.get('last_location') or '').strip()
    identifiers = (request.form.get('identifiers') or '').strip()

    if not name:
        return jsonify({"msg": "Name is required"}), 400

    # Validate NIC
    if national_id and not re.match(r'^\d{5}-\d{7}-\d{1}$', national_id):
        return jsonify({"msg": "Invalid National ID format. Use XXXXX-XXXXXXX-X"}), 400

    main_photo, saved_embeddings, err = process_case_photos(files, name)
    if err:
        return jsonify({"msg": err}), 400

    new_case = MissingPerson(
        name=name,
        national_id=national_id,
        last_location=last_location,
        identifiers=identifiers,
        photo_path=main_photo,
        embedding_blob=saved_embeddings,
        reporter=get_jwt_identity(),
    )

    db.session.add(new_case)
    db.session.commit()
    audit_logger().info("CASE_CREATE id=%s name=%s by=%s", new_case.id, name, get_jwt_identity())

    return jsonify({"msg": "Case created", "id": new_case.id}), 201

@cases_bp.route('/<int:case_id>', methods=['GET'])
def get_case(case_id):
    case = MissingPerson.query.get_or_404(case_id)
    
    # Gather every uploaded photo for this case. The files live under the
    # configured UPLOAD_FOLDER in a per-person subdirectory; the public URL is
    # the directory of the stored photo_path (e.g. /static/uploads/Name).
    additional_photos = []
    if case.photo_path:
        url_dir = os.path.dirname(case.photo_path)                  # /static/uploads/Name
        person_subdir = os.path.basename(url_dir)                   # Name
        abs_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], person_subdir)
        allowed = current_app.config['ALLOWED_IMAGE_EXTENSIONS']

        if os.path.isdir(abs_dir):
            for f in sorted(os.listdir(abs_dir)):
                ext = f.rsplit('.', 1)[-1].lower() if '.' in f else ''
                if ext in allowed:
                    additional_photos.append(f"{url_dir}/{f}")
                    
    return jsonify({
        "id": case.id,
        "name": case.name,
        "national_id": case.national_id,
        "last_location": case.last_location,
        "identifiers": case.identifiers,
        "status": case.status,
        "photo_path": case.photo_path,
        "photos": additional_photos,
        "reporter": case.reporter,
    }), 200


@cases_bp.route('/<int:case_id>', methods=['PUT'])
@login_required
def edit_case(case_id):
    """Edit a case's details. Allowed for an admin or the case's own reporter."""
    case = MissingPerson.query.get_or_404(case_id)
    identity = get_jwt_identity()
    role = (get_jwt() or {}).get('role')
    if role != 'admin' and (case.reporter or None) != identity:
        return jsonify({"msg": "You can only edit a case you reported."}), 403

    data = request.get_json(silent=True) or {}
    if 'name' in data:
        name = (data.get('name') or '').strip()
        if not name:
            return jsonify({"msg": "Name cannot be empty"}), 400
        case.name = name
    if 'national_id' in data:
        nid = (data.get('national_id') or '').strip()
        if nid and not re.match(r'^\d{5}-\d{7}-\d{1}$', nid):
            return jsonify({"msg": "Invalid National ID format. Use XXXXX-XXXXXXX-X"}), 400
        case.national_id = nid
    if 'last_location' in data:
        case.last_location = (data.get('last_location') or '').strip()
    if 'identifiers' in data:
        case.identifiers = (data.get('identifiers') or '').strip()

    db.session.commit()
    audit_logger().info("CASE_EDIT id=%s by=%s", case_id, identity)
    return jsonify({"msg": "Case updated"}), 200

@cases_bp.route('/<int:case_id>/sightings', methods=['GET'])
def case_sightings(case_id):
    """Public: sightings for one case, so the family/reporter viewing the case
    can see where the person was spotted and the image the system matched on.

    Only surfaces *meaningful* sightings — those that updated the location or
    produced a face-recognition result — newest first.
    """
    MissingPerson.query.get_or_404(case_id)
    result = []

    # Social-media sightings (post analysis).
    rows = (FacebookSighting.query
            .filter_by(missing_person_id=case_id)
            .order_by(FacebookSighting.created_at.desc())
            .limit(20).all())
    for s in rows:
        images = s.image_paths.split(",") if s.image_paths else []
        if not s.new_location and not images:
            continue  # skip empty/noise entries
        result.append({
            "id": "social-%d" % s.id,
            "source": "social",
            "new_location": s.new_location,
            "previous_location": s.previous_location,
            "applied": s.applied,
            "match_score": s.match_score,
            "images": images,
            "face_match": s.face_match,
            "post_url": s.post_url,
            "camera_source": None,
            "confidence": None,
            "timestamp": s.created_at,
        })

    # Live-camera detections (surveillance stream) also alert the case page.
    alerts = (MatchAlert.query
              .filter_by(missing_person_id=case_id)
              .order_by(MatchAlert.timestamp.desc())
              .limit(20).all())
    for a in alerts:
        result.append({
            "id": "camera-%d" % a.id,
            "source": "camera",
            "new_location": None,
            "previous_location": None,
            "applied": False,
            "match_score": None,
            "images": [a.snapshot_path] if a.snapshot_path else [],
            "face_match": "Seen on camera",
            "post_url": None,
            "camera_source": a.camera_source,
            "confidence": round(a.confidence, 3) if a.confidence is not None else None,
            "status": a.status,
            "timestamp": a.timestamp,
        })

    result.sort(key=lambda r: r["timestamp"] or datetime.min, reverse=True)
    return jsonify(result), 200


@cases_bp.route('/<int:case_id>/status', methods=['PUT'])
@admin_required
def update_status(case_id):
    case = MissingPerson.query.get_or_404(case_id)
    status = (request.get_json(silent=True) or {}).get('status')

    if status not in ['active', 'solved']:
        return jsonify({"msg": "Invalid status"}), 400

    case.status = status
    db.session.commit()
    audit_logger().info("CASE_STATUS id=%s -> %s by=%s", case_id, status, get_jwt_identity())
    return jsonify({"msg": "Status updated", "status": case.status}), 200
