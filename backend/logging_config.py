"""
Application logging: console + rotating file handlers.

Call setup_logging(app) once during app creation. After that, use
`current_app.logger` or `logging.getLogger("locaite")` anywhere.
Security-relevant events are also written to a dedicated audit log.
"""

import logging
import os
from logging.handlers import RotatingFileHandler

_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def setup_logging(app):
    log_dir = app.config.get("LOG_DIR", os.path.join(os.getcwd(), "logs"))
    os.makedirs(log_dir, exist_ok=True)

    level = getattr(logging, str(app.config.get("LOG_LEVEL", "INFO")).upper(), logging.INFO)
    formatter = logging.Formatter(_FORMAT)

    # Root app logger -------------------------------------------------------
    app.logger.handlers.clear()
    app.logger.setLevel(level)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.setLevel(level)
    app.logger.addHandler(console)

    app_file = RotatingFileHandler(
        os.path.join(log_dir, "app.log"), maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    app_file.setFormatter(formatter)
    app_file.setLevel(level)
    app.logger.addHandler(app_file)

    # Dedicated security/audit logger --------------------------------------
    audit = logging.getLogger("locaite.audit")
    audit.handlers.clear()
    audit.setLevel(logging.INFO)
    audit.propagate = False
    audit_file = RotatingFileHandler(
        os.path.join(log_dir, "audit.log"), maxBytes=2_000_000, backupCount=10, encoding="utf-8"
    )
    audit_file.setFormatter(formatter)
    audit.addHandler(audit_file)
    audit.addHandler(console)

    # Quiet noisy third-party loggers.
    for noisy in ("werkzeug", "tensorflow", "PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    app.logger.info("Logging initialised (level=%s, dir=%s)", logging.getLevelName(level), log_dir)


def audit_logger():
    return logging.getLogger("locaite.audit")
