import os
import time
from datetime import datetime

import cv2
from flask import Blueprint, Response, current_app

from extensions import db
from models import MatchAlert, MissingPerson
from utils.face_recognition import FaceModel
from security import admin_required
from logging_config import audit_logger

stream_bp = Blueprint('stream', __name__)

# Camera source: 0 = default webcam, or an RTSP/HTTP URL via env.
camera_source = os.environ.get('CAMERA_SOURCE', '0')
if str(camera_source).isdigit():
    camera_source = int(camera_source)

MATCH_THRESHOLD = 0.65
PROCESS_EVERY_N = 10
# Don't spam alerts: at most one new alert per person within this window.
ALERT_COOLDOWN_SECONDS = 30

# person_id -> last alert epoch seconds (process-local; resets on restart).
_last_alert_at = {}


def _save_snapshot(app, frame, box, person_id):
    """Persist the cropped live face so admins get a true side-by-side review."""
    try:
        x, y, w, h = box
        x1, y1 = max(0, x), max(0, y)
        crop = frame[y1:y1 + h, x1:x1 + w]
        if crop.size == 0:
            return None
        snap_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'snapshots')
        os.makedirs(snap_dir, exist_ok=True)
        fname = f"match_{person_id}_{int(time.time() * 1000)}.jpg"
        cv2.imwrite(os.path.join(snap_dir, fname), crop)
        return f"/static/uploads/snapshots/{fname}"
    except Exception:
        app.logger.exception("Failed to save match snapshot")
        return None


def _maybe_create_alert(app, frame, box, person, distance):
    """Create a MatchAlert with cooldown-based de-duplication."""
    now = time.time()
    last = _last_alert_at.get(person.id, 0)
    if now - last < ALERT_COOLDOWN_SECONDS:
        return  # suppress duplicate/noise alerts within the cooldown window
    _last_alert_at[person.id] = now

    snapshot = _save_snapshot(app, frame, box, person.id)
    alert = MatchAlert(
        missing_person_id=person.id,
        confidence=float(distance),
        status='pending',
        snapshot_path=snapshot,
        timestamp=datetime.utcnow(),
    )
    db.session.add(alert)
    db.session.commit()
    audit_logger().info("MATCH_ALERT person_id=%s name=%s dist=%.3f", person.id, person.name, distance)


def gen_frames(app):
    camera = cv2.VideoCapture(camera_source)
    model = FaceModel.get_instance()
    frame_count = 0

    while True:
        success, frame = camera.read()
        if not success:
            camera.release()
            time.sleep(1)
            camera = cv2.VideoCapture(camera_source)
            continue

        frame_count += 1

        if frame_count % PROCESS_EVERY_N == 0:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            try:
                detections = model.detect_faces(rgb)
                for det in detections:
                    box = det['box']
                    face_img = model.extract_face(rgb, box)
                    if face_img.size == 0:
                        continue

                    emb = model.get_embedding(face_img)

                    with app.app_context():
                        active_cases = MissingPerson.query.filter_by(status='active').all()
                        min_dist = float('inf')
                        best_match = None
                        for case in active_cases:
                            if not case.embedding_blob:
                                continue
                            for db_emb in case.embedding_blob:
                                dist = model.distance(emb, db_emb)
                                if dist < min_dist:
                                    min_dist = dist
                                    best_match = case

                        color = (0, 0, 255)  # Red (Unknown) in BGR
                        label = "Unknown"

                        if best_match and min_dist < MATCH_THRESHOLD:
                            color = (0, 255, 0)  # Green (Match)
                            label = f"{best_match.name} ({min_dist:.2f})"
                            _maybe_create_alert(app, frame, box, best_match, min_dist)

                        cv2.rectangle(frame, (box[0], box[1]),
                                      (box[0] + box[2], box[1] + box[3]), color, 2)
                        cv2.putText(frame, label, (box[0], box[1] - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
            except Exception:
                app.logger.exception("Stream frame processing error")

        ret, buffer = cv2.imencode('.jpg', frame)
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')


@stream_bp.route('/feed')
@admin_required
def video_feed():
    return Response(
        gen_frames(current_app._get_current_object()),
        mimetype='multipart/x-mixed-replace; boundary=frame',
    )
