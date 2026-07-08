import os
import secrets

from flask import Flask, send_from_directory, abort, jsonify, request
from flask_cors import CORS
from flask_jwt_extended import JWTManager

from extensions import db
from config import get_config
from logging_config import setup_logging, audit_logger

# The static HTML frontend lives next to the backend folder.
FRONTEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'new_front_end')
)


def create_app(config_name=None):
    app = Flask(__name__)
    app.config.from_object(get_config(config_name))

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    setup_logging(app)

    # Extensions ----------------------------------------------------------
    CORS(app, resources={r"/api/*": {"origins": app.config['CORS_ORIGINS']}},
         supports_credentials=True)
    db.init_app(app)
    jwt = JWTManager(app)

    _register_jwt_handlers(jwt)
    _register_security_headers(app)
    _register_error_handlers(app)

    # Blueprints ----------------------------------------------------------
    from routes.auth import auth_bp
    from routes.cases import cases_bp
    from routes.admin import admin_bp
    from routes.stream import stream_bp
    from routes.fb import fb_bp

    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(cases_bp, url_prefix='/api/cases')
    app.register_blueprint(admin_bp, url_prefix='/api/admin')
    app.register_blueprint(stream_bp, url_prefix='/api/stream')
    app.register_blueprint(fb_bp, url_prefix='/api/admin/fb')

    @app.route('/api/health')
    def health():
        return jsonify(status='ok'), 200

    _register_uploads(app)
    _register_frontend(app)

    with app.app_context():
        db.create_all()
        _seed_admin(app)

    app.logger.info("locAIte app created (env=%s, debug=%s)",
                    os.environ.get('APP_ENV', 'production'), app.config['DEBUG'])
    return app


def _register_jwt_handlers(jwt):
    @jwt.unauthorized_loader
    def _missing(reason):
        return jsonify(msg="Authentication required"), 401

    @jwt.invalid_token_loader
    def _invalid(reason):
        return jsonify(msg="Invalid token"), 401

    @jwt.expired_token_loader
    def _expired(header, payload):
        return jsonify(msg="Token expired"), 401


def _register_security_headers(app):
    @app.after_request
    def _headers(resp):
        resp.headers['X-Content-Type-Options'] = 'nosniff'
        resp.headers['X-Frame-Options'] = 'SAMEORIGIN'
        resp.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        resp.headers['X-XSS-Protection'] = '1; mode=block'
        # Never cache API responses (may contain authenticated data).
        if request.path.startswith('/api/'):
            resp.headers['Cache-Control'] = 'no-store'
        return resp


def _register_error_handlers(app):
    @app.errorhandler(404)
    def _404(e):
        return jsonify(msg="Not found"), 404

    @app.errorhandler(413)
    def _413(e):
        return jsonify(msg="Uploaded file too large"), 413

    @app.errorhandler(500)
    def _500(e):
        app.logger.exception("Unhandled server error")
        return jsonify(msg="Internal server error"), 500


def _register_uploads(app):
    """Serve uploaded case photos + match snapshots from UPLOAD_FOLDER.

    Case photo_path / snapshot_path are stored as '/static/uploads/...'. By
    serving that prefix explicitly from UPLOAD_FOLDER (instead of relying on
    Flask's default static dir), UPLOAD_FOLDER can live on a persistent volume
    (e.g. /data/uploads) so photos survive restarts/redeploys.
    """
    upload_root = os.path.abspath(app.config['UPLOAD_FOLDER'])

    @app.route('/static/uploads/<path:filename>')
    def uploaded_file(filename):
        full = os.path.abspath(os.path.join(upload_root, filename))
        # Block path traversal outside the upload root.
        if not full.startswith(upload_root):
            abort(404)
        if os.path.isfile(full):
            return send_from_directory(upload_root, filename)
        abort(404)


def _register_frontend(app):
    @app.route('/')
    def index():
        return send_from_directory(FRONTEND_DIR, 'index.html')

    @app.route('/<path:filename>')
    def frontend_files(filename):
        if filename.startswith('api/'):
            abort(404)
        # Prevent path traversal outside the frontend dir.
        full = os.path.abspath(os.path.join(FRONTEND_DIR, filename))
        if not full.startswith(FRONTEND_DIR):
            abort(404)
        if os.path.isfile(full):
            return send_from_directory(FRONTEND_DIR, filename)
        if os.path.isfile(full + '.html'):
            return send_from_directory(FRONTEND_DIR, filename + '.html')
        abort(404)


def _seed_admin(app):
    from models import User
    from werkzeug.security import generate_password_hash

    if User.query.filter_by(username=app.config['ADMIN_USERNAME']).first():
        return

    password = app.config.get('ADMIN_PASSWORD')
    generated = False
    if not password:
        password = secrets.token_urlsafe(12)
        generated = True

    admin = User(
        username=app.config['ADMIN_USERNAME'],
        email=app.config['ADMIN_EMAIL'],
        first_name='System', last_name='Admin', middle_name='',
        password_hash=generate_password_hash(password),
        role='admin',
    )
    db.session.add(admin)
    db.session.commit()

    msg = "Seed admin '%s' created." % app.config['ADMIN_USERNAME']
    if generated:
        # Printed once to the server console/log; not stored in plaintext anywhere else.
        app.logger.warning("%s GENERATED PASSWORD (change immediately): %s", msg, password)
        audit_logger().warning("Admin account seeded with generated password.")
    else:
        app.logger.info("%s (password from ADMIN_PASSWORD env).", msg)


if __name__ == '__main__':
    app = create_app(os.environ.get('APP_ENV', 'development'))
    app.run(host='127.0.0.1', port=5000, debug=app.config['DEBUG'])
