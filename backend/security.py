"""
Authorisation helpers: JWT-backed role guards and a small login throttle.

Identity convention (set in routes/auth.py):
    create_access_token(identity=<username>, additional_claims={"role": ..., "uid": ...})
So the JWT 'sub' is always a string (RFC-compliant) and the role travels in a
custom claim that role_required() checks.
"""

import time
from collections import defaultdict
from functools import wraps

from flask import jsonify
from flask_jwt_extended import get_jwt, verify_jwt_in_request

from logging_config import audit_logger


def role_required(*roles):
    """Require a valid JWT whose 'role' claim is in `roles`. No roles -> any logged-in user."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                verify_jwt_in_request()
            except Exception:
                return jsonify({"msg": "Authentication required"}), 401
            claims = get_jwt()
            role = claims.get("role")
            if roles and role not in roles:
                audit_logger().warning(
                    "FORBIDDEN role=%s required=%s sub=%s", role, roles, claims.get("sub")
                )
                return jsonify({"msg": "Insufficient privileges"}), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def admin_required(fn):
    return role_required("admin")(fn)


def login_required(fn):
    return role_required()(fn)


class LoginThrottle:
    """In-memory sliding-window throttle. Good enough for a single-process deploy."""

    def __init__(self, max_attempts=10, window_seconds=300):
        self.max_attempts = max_attempts
        self.window = window_seconds
        self._hits = defaultdict(list)

    def _prune(self, key, now):
        self._hits[key] = [t for t in self._hits[key] if now - t < self.window]

    def is_blocked(self, key):
        now = time.time()
        self._prune(key, now)
        return len(self._hits[key]) >= self.max_attempts

    def record_failure(self, key):
        self._hits[key].append(time.time())

    def reset(self, key):
        self._hits.pop(key, None)
