"""
Admin endpoint for the Reddit analyzer.

  POST /api/admin/reddit/scan   body: {"query": "...", "subreddit": "...", "limit": 25}
                                Searches Reddit (official OAuth API) and runs each
                                post through the shared pipeline (name match ->
                                location extraction -> case update / sighting).
"""

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import get_jwt_identity

from security import admin_required
from logging_config import audit_logger
import fb_service
import reddit_service

reddit_bp = Blueprint('reddit', __name__)


@reddit_bp.route('/scan', methods=['POST'])
@admin_required
def scan():
    body = request.get_json(silent=True) or {}
    query = (body.get('query') or '').strip()
    subreddit = (body.get('subreddit') or '').strip() or None
    limit = body.get('limit', 25)

    if not query:
        return jsonify({"msg": "Enter a search query (e.g. a case name or 'missing person Karachi')."}), 400
    if not reddit_service.is_configured():
        return jsonify({
            "msg": "Reddit is not configured. Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET "
                   "(create a free app at reddit.com/prefs/apps), then redeploy."
        }), 400

    try:
        posts = reddit_service.fetch_reddit_posts(query, limit=limit, subreddit=subreddit)
        summary = fb_service.process_posts(posts)
    except Exception as e:
        current_app.logger.exception("Reddit scan failed")
        return jsonify({"msg": "Reddit scan failed", "error": str(e)}), 500

    audit_logger().info("REDDIT_SCAN by=%s query=%r sub=%s result=%s",
                        get_jwt_identity(), query, subreddit, summary)
    return jsonify(summary), 200
