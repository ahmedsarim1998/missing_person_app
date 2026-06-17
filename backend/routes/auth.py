import re

from flask import Blueprint, request, jsonify, current_app
from werkzeug.security import check_password_hash, generate_password_hash
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, get_jwt

from extensions import db
from models import User
from security import LoginThrottle
from logging_config import audit_logger

auth_bp = Blueprint('auth', __name__)

# One throttle per process. Limits configured from app config on first use.
_throttle = None

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
USERNAME_RE = re.compile(r'^[A-Za-z0-9_.-]{3,30}$')


def _get_throttle():
    global _throttle
    if _throttle is None:
        _throttle = LoginThrottle(
            max_attempts=current_app.config['LOGIN_MAX_ATTEMPTS'],
            window_seconds=current_app.config['LOGIN_WINDOW_SECONDS'],
        )
    return _throttle


def _make_token(user):
    return create_access_token(
        identity=user.username,
        additional_claims={"role": user.role, "uid": user.id},
    )


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    client_ip = request.remote_addr or 'unknown'
    throttle = _get_throttle()
    key = f"{client_ip}:{username.lower()}"

    if throttle.is_blocked(key):
        audit_logger().warning("LOGIN_BLOCKED ip=%s user=%s (too many attempts)", client_ip, username)
        return jsonify({"msg": "Too many failed attempts. Try again later."}), 429

    if not username or not password:
        return jsonify({"msg": "Username and password are required"}), 400

    user = User.query.filter_by(username=username).first()
    if user and check_password_hash(user.password_hash, password):
        throttle.reset(key)
        audit_logger().info("LOGIN_OK ip=%s user=%s role=%s", client_ip, username, user.role)
        return jsonify(
            access_token=_make_token(user),
            role=user.role,
            username=user.username,
        ), 200

    throttle.record_failure(key)
    audit_logger().warning("LOGIN_FAIL ip=%s user=%s", client_ip, username)
    return jsonify({"msg": "Bad username or password"}), 401


@auth_bp.route('/signup', methods=['POST'])
def signup():
    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    email = (data.get('email') or '').strip().lower()
    first_name = (data.get('first_name') or '').strip()
    last_name = (data.get('last_name') or '').strip()
    middle_name = (data.get('middle_name') or '').strip()

    # Validation
    if not USERNAME_RE.match(username):
        return jsonify({"msg": "Username must be 3-30 chars (letters, digits, . _ -)"}), 400
    if not EMAIL_RE.match(email):
        return jsonify({"msg": "Invalid email address"}), 400
    if len(password) < 8:
        return jsonify({"msg": "Password must be at least 8 characters"}), 400
    if not first_name or not last_name:
        return jsonify({"msg": "First and last name are required"}), 400

    if User.query.filter((User.username == username) | (User.email == email)).first():
        return jsonify({"msg": "Username or Email already exists"}), 409

    new_user = User(
        username=username, email=email,
        first_name=first_name, last_name=last_name, middle_name=middle_name,
        password_hash=generate_password_hash(password),
        role='user',  # privilege escalation impossible from public signup
    )
    db.session.add(new_user)
    db.session.commit()
    audit_logger().info("SIGNUP user=%s email=%s", username, email)

    return jsonify({"msg": "User created"}), 201


@auth_bp.route('/me', methods=['GET'])
@jwt_required()
def me():
    claims = get_jwt()
    return jsonify(
        username=get_jwt_identity(),
        role=claims.get('role'),
        uid=claims.get('uid'),
    ), 200
