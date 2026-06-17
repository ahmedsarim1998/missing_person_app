import re
from flask import Blueprint, request, jsonify, current_app
from extensions import db
from models import MissingPerson
from werkzeug.utils import secure_filename
import os
import cv2
from utils.face_recognition import FaceModel
from security import login_required, admin_required
from flask_jwt_extended import get_jwt_identity
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

    # Save photos
    person_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], secure_filename(name))
    os.makedirs(person_dir, exist_ok=True)

    saved_embeddings = []
    main_photo = None

    model = FaceModel.get_instance()

    for i, file in enumerate(files):
        if not file or file.filename == '':
            continue
        if not _allowed(file.filename):
            return jsonify({"msg": f"Unsupported file type: {file.filename}"}), 400
        filename = secure_filename(file.filename)
        path = os.path.join(person_dir, filename)
        file.save(path)

        if i == 0:
            main_photo = f"/static/uploads/{secure_filename(name)}/{filename}"

        # Process embedding
        img = cv2.imread(path)
        if img is None:
            continue
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        detections = model.detect_faces(rgb)
        if detections:
            best = max(detections, key=lambda d: d['box'][2] * d['box'][3])
            face = model.extract_face(rgb, best['box'])
            emb = model.get_embedding(face)
            saved_embeddings.append(emb)

    if not saved_embeddings:
        return jsonify({"msg": "No faces detected in uploaded photos"}), 400

    # Average embedding or save list? 
    # For MVP, let's save the list.
    new_case = MissingPerson(
        name=name,
        national_id=national_id,
        last_location=last_location,
        identifiers=identifiers,
        photo_path=main_photo,
        embedding_blob=saved_embeddings
    )
    
    db.session.add(new_case)
    db.session.commit()
    audit_logger().info("CASE_CREATE id=%s name=%s by=%s", new_case.id, name, get_jwt_identity())

    return jsonify({"msg": "Case created", "id": new_case.id}), 201

@cases_bp.route('/<int:case_id>', methods=['GET'])
def get_case(case_id):
    case = MissingPerson.query.get_or_404(case_id)
    
    # Get all photos
    additional_photos = []
    if case.photo_path:
        # Extract dir from photo path (e.g., /static/uploads/Name/file.jpg)
        # We need absolute path to listdir
        # Assuming photo_path is relative to root like /static/...
        
        # This is a bit hacky, but works if we follow naming convention
        rel_dir = os.path.dirname(case.photo_path).lstrip('/') # static/uploads/Name
        abs_dir = os.path.join(os.getcwd(), rel_dir)
        
        if os.path.exists(abs_dir):
            for f in os.listdir(abs_dir):
                if f.lower().endswith(('.png', '.jpg', '.jpeg')):
                    additional_photos.append(f"/{rel_dir}/{f}")
                    
    return jsonify({
        "id": case.id,
        "name": case.name,
        "national_id": case.national_id,
        "last_location": case.last_location,
        "identifiers": case.identifiers,
        "status": case.status,
        "photo_path": case.photo_path,
        "photos": additional_photos
    }), 200

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
