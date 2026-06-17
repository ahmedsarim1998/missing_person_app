from datetime import datetime

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity

from extensions import db
from models import MissingPerson, MatchAlert
from security import admin_required
from logging_config import audit_logger

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/dashboard', methods=['GET'])
@admin_required
def dashboard_stats():
    total_cases = MissingPerson.query.count()
    active_cases = MissingPerson.query.filter_by(status='active').count()
    pending_matches = MatchAlert.query.filter_by(status='pending').count()

    return jsonify({
        "total_cases": total_cases,
        "active_cases": active_cases,
        "pending_matches": pending_matches,
    }), 200


@admin_bp.route('/matches', methods=['GET'])
@admin_required
def get_matches():
    matches = (MatchAlert.query
               .filter_by(status='pending')
               .order_by(MatchAlert.confidence.asc())
               .all())
    result = []
    for m in matches:
        result.append({
            "id": m.id,
            "person_name": m.person.name,
            "confidence": m.confidence,
            "timestamp": m.timestamp,
            "person_photo": m.person.photo_path,   # stored reference photo
            "snapshot": m.snapshot_path,           # live capture for side-by-side review
        })
    return jsonify(result), 200


@admin_bp.route('/match/<int:match_id>', methods=['POST'])
@admin_required
def resolve_match(match_id):
    action = (request.get_json(silent=True) or {}).get('action')  # 'confirm' or 'reject'

    match = MatchAlert.query.get_or_404(match_id)
    if action == 'confirm':
        match.status = 'confirmed'
    elif action == 'reject':
        match.status = 'rejected'
    else:
        return jsonify({"msg": "Invalid action"}), 400

    # Audit trail: who resolved it and when.
    match.resolved_by = get_jwt_identity()
    match.resolved_at = datetime.utcnow()
    db.session.commit()
    audit_logger().info("MATCH_%s id=%s person_id=%s by=%s",
                        match.status.upper(), match_id, match.missing_person_id, match.resolved_by)
    return jsonify({"msg": "Match resolved", "status": match.status}), 200
