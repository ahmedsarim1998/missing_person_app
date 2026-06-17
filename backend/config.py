"""
Centralised configuration for the locAIte backend.

Secrets are read from the environment (loaded from a local .env file in
development via python-dotenv). If no secret is supplied a strong random one is
generated and persisted to `instance/secret.key` so tokens survive restarts
without ever shipping a hard-coded key in source control.
"""

import os
import secrets

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # python-dotenv is optional; env vars still work without it
    pass

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
os.makedirs(INSTANCE_DIR, exist_ok=True)


def _persisted_secret(name, env_value):
    """Return env secret if set, else load/generate a persisted random secret."""
    if env_value:
        return env_value
    path = os.path.join(INSTANCE_DIR, name)
    if os.path.isfile(path):
        with open(path, "r") as fh:
            value = fh.read().strip()
            if value:
                return value
    value = secrets.token_urlsafe(48)
    with open(path, "w") as fh:
        fh.write(value)
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass
    return value


def _as_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


class BaseConfig:
    SECRET_KEY = _persisted_secret("secret.key", os.environ.get("SECRET_KEY"))
    JWT_SECRET_KEY = _persisted_secret("jwt.key", os.environ.get("JWT_SECRET_KEY"))

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///missing_persons.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UPLOAD_FOLDER = os.environ.get(
        "UPLOAD_FOLDER", os.path.join(os.getcwd(), "static", "uploads")
    )
    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_CONTENT_LENGTH_MB", "25")) * 1024 * 1024
    ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

    # --- Live stream / recognition tuning -------------------------------
    CAMERA_SOURCE = os.environ.get("CAMERA_SOURCE", "0")   # 0 = webcam, or RTSP/HTTP URL
    STREAM_TARGET_FPS = int(os.environ.get("STREAM_TARGET_FPS", "25"))      # output smoothness
    STREAM_RECOG_INTERVAL = float(os.environ.get("STREAM_RECOG_INTERVAL", "0.4"))  # secs between recognitions
    STREAM_JPEG_QUALITY = int(os.environ.get("STREAM_JPEG_QUALITY", "70"))  # 1-100
    STREAM_DETECT_WIDTH = int(os.environ.get("STREAM_DETECT_WIDTH", "640"))  # downscale width for detection
    STREAM_IDLE_TIMEOUT = float(os.environ.get("STREAM_IDLE_TIMEOUT", "8"))  # release camera after N idle secs
    EMBED_CACHE_TTL = float(os.environ.get("EMBED_CACHE_TTL", "10"))         # refresh case embeddings every N secs
    ALERT_COOLDOWN_SECONDS = int(os.environ.get("ALERT_COOLDOWN_SECONDS", "30"))
    MATCH_THRESHOLD = float(os.environ.get("MATCH_THRESHOLD", "0.65"))

    # Access-token lifetime (minutes)
    from datetime import timedelta
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        minutes=int(os.environ.get("JWT_EXPIRES_MIN", "720"))
    )
    # Allow the live stream <img> tag to authenticate via ?jwt= query param.
    JWT_TOKEN_LOCATION = ["headers", "query_string"]
    JWT_QUERY_STRING_NAME = "jwt"

    # Comma-separated allowed CORS origins. Default: same-origin only.
    CORS_ORIGINS = [
        o.strip()
        for o in os.environ.get("CORS_ORIGINS", "http://localhost:5000,http://127.0.0.1:5000").split(",")
        if o.strip()
    ]

    # Facebook analyzer
    FB_GROUP = os.environ.get("FB_GROUP")
    FB_PAGES = int(os.environ.get("FB_PAGES", "2"))
    FB_COOKIES = os.environ.get("FB_COOKIES")

    # Seed admin (first boot only). Override via env in production.
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@locaite.com")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")  # if None -> random, printed once

    # Login throttling
    LOGIN_MAX_ATTEMPTS = int(os.environ.get("LOGIN_MAX_ATTEMPTS", "10"))
    LOGIN_WINDOW_SECONDS = int(os.environ.get("LOGIN_WINDOW_SECONDS", "300"))

    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
    LOG_DIR = os.environ.get("LOG_DIR", os.path.join(BASE_DIR, "logs"))

    DEBUG = False
    TESTING = False


class DevelopmentConfig(BaseConfig):
    DEBUG = _as_bool(os.environ.get("FLASK_DEBUG"), default=False)


class ProductionConfig(BaseConfig):
    DEBUG = False


class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")
    SECRET_KEY = "test-secret"
    JWT_SECRET_KEY = "test-jwt-secret"
    LOGIN_MAX_ATTEMPTS = int(os.environ.get("LOGIN_MAX_ATTEMPTS", "1000"))
    WTF_CSRF_ENABLED = False


_CONFIGS = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def get_config(name=None):
    name = (name or os.environ.get("APP_ENV", "production")).lower()
    return _CONFIGS.get(name, ProductionConfig)
