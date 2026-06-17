"""
Admin endpoints for the Facebook analyzer.

  POST /api/admin/fb/scan        run a scan now -> {scanned, matched, updated, skipped}
                                 body: {"demo": true} to synthesize posts from
                                 active cases, or {"posts": [...]} to process given posts.
  GET  /api/admin/fb/sightings   recent location updates (audit log) for the dashboard.
"""

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import get_jwt_identity
from models import FacebookSighting
from security import admin_required
from logging_config import audit_logger
import fb_service

fb_bp = Blueprint('fb', __name__)


@fb_bp.route('/scan', methods=['POST'])
@admin_required
def scan():
    body = request.get_json(silent=True) or {}
    demo = bool(body.get('demo'))
    posts = body.get('posts')  # optional explicit list of {post_id,text,post_url}
    try:
        summary = fb_service.run_scan(current_app.config, posts=posts, demo=demo)
    except Exception as e:
        current_app.logger.exception("FB scan failed")
        # Scraping is the brittle part; surface the error instead of 500-ing blind.
        return jsonify({"msg": "Scan failed", "error": str(e)}), 500
    audit_logger().info("FB_SCAN by=%s demo=%s result=%s", get_jwt_identity(), demo, summary)
    return jsonify(summary), 200


@fb_bp.route('/sightings', methods=['GET'])
@admin_required
def sightings():
    rows = (FacebookSighting.query
            .order_by(FacebookSighting.created_at.desc())
            .limit(50).all())
    result = []
    for s in rows:
        result.append({
            "id": s.id,
            "person_name": s.matched_name,
            "match_score": s.match_score,
            "previous_location": s.previous_location,
            "new_location": s.new_location,
            "applied": s.applied,
            "post_url": s.post_url,
            "timestamp": s.created_at,
        })
    return jsonify(result), 200
