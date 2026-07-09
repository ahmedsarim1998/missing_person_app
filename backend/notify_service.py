"""
Reporter notifications: when a case gets a new sighting/location update or a
face-recognition match, alert the person who reported it.

Delivery is best-effort and configurable:
  * The alert is ALWAYS recorded in the audit log (so there is a real record
    that the reporter was notified, visible without any external service).
  * If SMTP is configured (SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASS), an email is
    also sent to the case's reporter_email.

This function never raises — a notification problem must not break the analysis
or detection pipeline.
"""

import os
import smtplib
from email.message import EmailMessage

from logging_config import audit_logger


def _smtp_configured():
    return all(os.environ.get(k) for k in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS"))


def _send_email(to_email, subject, body):
    host = os.environ["SMTP_HOST"]
    port = int(os.environ["SMTP_PORT"])
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASS"]
    sender = os.environ.get("SMTP_FROM", user)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_email
    msg.set_content(body)

    with smtplib.SMTP(host, port, timeout=15) as server:
        server.starttls()
        server.login(user, password)
        server.send_message(msg)


def notify_case_update(case, subject, message):
    """Alert a case's reporter. Records to the audit log always; emails if
    SMTP is configured and the case has a reporter_email. Never raises."""
    try:
        email = getattr(case, "reporter_email", None)
        phone = getattr(case, "reporter_phone", None)
        audit_logger().info(
            "NOTIFY case_id=%s person=%s email=%s phone=%s :: %s",
            case.id, case.name, email or "-", phone or "-", subject,
        )
        if email and _smtp_configured():
            _send_email(email, subject, message)
            audit_logger().info("NOTIFY_EMAIL_SENT case_id=%s to=%s", case.id, email)
    except Exception:
        # Notifications are best-effort; log and move on.
        try:
            audit_logger().warning("NOTIFY_FAILED case_id=%s", getattr(case, "id", "?"))
        except Exception:
            pass
