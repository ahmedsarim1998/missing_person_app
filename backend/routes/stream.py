"""
Live surveillance stream — decoupled, smooth, multi-viewer.

Design (why it's smooth):
  * ONE background capture thread continuously grabs frames and keeps only the
    latest one (no buffer build-up / lag).
  * A SEPARATE recognition thread runs MTCNN+FaceNet at a fixed cadence on a
    downscaled copy, so heavy ML never blocks frame delivery.
  * Active-case embeddings are cached in memory and refreshed periodically
    instead of hitting the DB every frame.
  * Each HTTP viewer just draws the latest cached annotations onto the latest
    frame and yields at a target FPS. Multiple viewers share one camera.
  * The camera is opened on the first viewer and released shortly after the last
    one disconnects.
"""

import re
import threading
import time
from datetime import datetime

import cv2
import numpy as np
from flask import Blueprint, Response, current_app, request, jsonify
from flask_jwt_extended import get_jwt_identity

from extensions import db
from models import MatchAlert, MissingPerson
from utils.face_recognition import FaceModel
from security import admin_required
from logging_config import audit_logger

stream_bp = Blueprint('stream', __name__)

# Accepted camera sources: a numeric webcam index, or an RTSP/RTMP/HTTP(S) URL
# (an IP camera / phone-camera stream). Anything else is rejected to keep the
# server from being pointed at arbitrary local resources.
_SOURCE_URL_RE = re.compile(r'^(?:rtsp|rtmp|http|https)://', re.IGNORECASE)


def _normalize_source(raw):
    """Return an int (webcam index) or a validated URL string, else None."""
    src = str(raw).strip()
    if not src:
        return None
    if src.isdigit():
        return int(src)
    if _SOURCE_URL_RE.match(src):
        return src
    return None


def _placeholder(text="Connecting to camera…", w=960, h=540):
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:] = (20, 20, 24)
    size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1.0, 2)[0]
    cv2.putText(img, text, ((w - size[0]) // 2, (h + size[1]) // 2),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (200, 200, 200), 2)
    return img


class StreamManager:
    """One per process. Owns the camera + recognition threads."""

    _instance = None
    _instance_lock = threading.Lock()

    @classmethod
    def instance(cls, app):
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls(app)
            return cls._instance

    def __init__(self, app):
        self.app = app
        cfg = app.config
        src = cfg.get('CAMERA_SOURCE', '0')
        self.source = int(src) if str(src).isdigit() else src
        self.target_fps = cfg['STREAM_TARGET_FPS']
        self.recog_interval = cfg['STREAM_RECOG_INTERVAL']
        self.jpeg_quality = cfg['STREAM_JPEG_QUALITY']
        self.detect_width = cfg['STREAM_DETECT_WIDTH']
        self.idle_timeout = cfg['STREAM_IDLE_TIMEOUT']
        self.embed_ttl = cfg['EMBED_CACHE_TTL']
        self.cooldown = cfg['ALERT_COOLDOWN_SECONDS']
        self.threshold = cfg['MATCH_THRESHOLD']

        self._frame_lock = threading.Lock()
        self._latest = None                 # latest raw BGR frame
        self._annotations = []              # [{box,label,color}]
        self._status = "offline"

        self._viewers = 0
        self._viewers_lock = threading.Lock()
        self._running = False
        self._source_lock = threading.Lock()
        self._last_view_ts = 0.0
        self._capture_thread = None
        self._recog_thread = None

        self._emb_cache = []                # [(id, name, [np.ndarray, ...])]
        self._emb_cache_ts = 0.0
        self._last_alert_at = {}

    # ---- lifecycle ----------------------------------------------------
    def _ensure_running(self):
        if self._running:
            return
        self._running = True
        self._status = "starting"
        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._recog_thread = threading.Thread(target=self._recognition_loop, daemon=True)
        self._capture_thread.start()
        self._recog_thread.start()
        self.app.logger.info("Stream started (source=%s)", self.source)

    def _stop(self):
        self._running = False
        self._status = "offline"
        with self._frame_lock:
            self._latest = None
            self._annotations = []
        self.app.logger.info("Stream stopped (no viewers)")

    def add_viewer(self):
        with self._viewers_lock:
            self._viewers += 1
            self._last_view_ts = time.time()
            self._ensure_running()

    def remove_viewer(self):
        with self._viewers_lock:
            self._viewers = max(0, self._viewers - 1)
            self._last_view_ts = time.time()

    # ---- runtime camera source ---------------------------------------
    def current_source(self):
        with self._source_lock:
            return str(self.source)

    def set_source(self, normalized):
        """Swap the camera source at runtime. `normalized` is an int index or a
        validated URL (see _normalize_source). The capture loop notices the
        change on its next iteration and reconnects — no restart needed."""
        with self._source_lock:
            self.source = normalized
        self.app.logger.info("Stream source changed to %s", normalized)

    # ---- capture ------------------------------------------------------
    def _open_camera(self):
        cap = cv2.VideoCapture(self.source)
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # keep latency low
        except Exception:
            pass
        return cap

    def _capture_loop(self):
        open_src = self.source
        cap = self._open_camera()
        fail_count = 0
        while self._running:
            # Auto-release the camera if nobody is watching.
            if self._viewers == 0 and (time.time() - self._last_view_ts) > self.idle_timeout:
                break

            # Hot-swap: reconnect if an admin changed the source at runtime.
            if self.source != open_src:
                cap.release()
                open_src = self.source
                cap = self._open_camera()
                fail_count = 0
                self._status = "starting"
                with self._frame_lock:
                    self._latest = _placeholder("Connecting to camera…")
                continue

            ok, frame = cap.read()
            if not ok:
                fail_count += 1
                self._status = "no-camera"
                with self._frame_lock:
                    self._latest = _placeholder("No camera signal")
                if fail_count % 30 == 0:
                    cap.release()
                    cap = self._open_camera()
                time.sleep(0.2)
                continue

            fail_count = 0
            self._status = "live"
            with self._frame_lock:
                self._latest = frame

        cap.release()
        self._running = False
        self._status = "offline"

    # ---- recognition --------------------------------------------------
    def _refresh_embeddings(self):
        now = time.time()
        if self._emb_cache and (now - self._emb_cache_ts) < self.embed_ttl:
            return
        cache = []
        with self.app.app_context():
            for case in MissingPerson.query.filter_by(status='active').all():
                if case.embedding_blob:
                    cache.append((case.id, case.name, list(case.embedding_blob)))
        self._emb_cache = cache
        self._emb_cache_ts = now

    def _recognition_loop(self):
        model = None
        while self._running:
            start = time.time()
            with self._frame_lock:
                frame = None if self._latest is None else self._latest.copy()

            if frame is None or self._status not in ("live",):
                time.sleep(self.recog_interval)
                continue

            if model is None:
                self._status = "loading-model"
                model = FaceModel.get_instance()  # one-time TensorFlow load
                self._status = "live"

            try:
                self._refresh_embeddings()
                annotations = self._detect_and_match(model, frame)
                with self._frame_lock:
                    self._annotations = annotations
            except Exception:
                self.app.logger.exception("Recognition cycle failed")

            elapsed = time.time() - start
            time.sleep(max(0.0, self.recog_interval - elapsed))

    def _detect_and_match(self, model, frame):
        h, w = frame.shape[:2]
        scale = self.detect_width / float(w) if w > self.detect_width else 1.0
        small = cv2.resize(frame, (int(w * scale), int(h * scale))) if scale < 1.0 else frame

        rgb_small = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        rgb_full = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        detections = model.detect_faces(rgb_small)
        annotations = []
        for det in detections:
            bx = det['box']
            box = [int(bx[0] / scale), int(bx[1] / scale),
                   int(bx[2] / scale), int(bx[3] / scale)]

            face = model.extract_face(rgb_full, box)
            if face.size == 0:
                continue
            emb = model.get_embedding(face)

            min_dist, best = float('inf'), None
            for cid, name, embs in self._emb_cache:
                for db_emb in embs:
                    d = model.distance(emb, db_emb)
                    if d < min_dist:
                        min_dist, best = d, (cid, name)

            if best and min_dist < self.threshold:
                label = "%s (%.2f)" % (best[1], min_dist)
                annotations.append({"box": box, "label": label, "color": (0, 200, 0)})
                self._maybe_alert(frame, box, best[0], best[1], min_dist)
            else:
                annotations.append({"box": box, "label": "Unknown", "color": (0, 0, 255)})
        return annotations

    def _maybe_alert(self, frame, box, person_id, name, distance):
        now = time.time()
        if now - self._last_alert_at.get(person_id, 0) < self.cooldown:
            return
        self._last_alert_at[person_id] = now
        snapshot = self._save_snapshot(frame, box, person_id)
        with self.app.app_context():
            db.session.add(MatchAlert(
                missing_person_id=person_id, confidence=float(distance),
                status='pending', snapshot_path=snapshot, timestamp=datetime.utcnow(),
            ))
            db.session.commit()
        audit_logger().info("MATCH_ALERT person_id=%s name=%s dist=%.3f", person_id, name, distance)

    def _save_snapshot(self, frame, box, person_id):
        try:
            import os
            x, y, bw, bh = box
            crop = frame[max(0, y):y + bh, max(0, x):x + bw]
            if crop.size == 0:
                return None
            snap_dir = os.path.join(self.app.config['UPLOAD_FOLDER'], 'snapshots')
            os.makedirs(snap_dir, exist_ok=True)
            fname = "match_%s_%d.jpg" % (person_id, int(time.time() * 1000))
            cv2.imwrite(os.path.join(snap_dir, fname), crop)
            return "/static/uploads/snapshots/%s" % fname
        except Exception:
            self.app.logger.exception("Snapshot save failed")
            return None

    # ---- output -------------------------------------------------------
    def frames(self):
        self.add_viewer()
        interval = 1.0 / max(1, self.target_fps)
        enc = [int(cv2.IMWRITE_JPEG_QUALITY), self.jpeg_quality]
        try:
            last = 0.0
            while True:
                now = time.time()
                wait = interval - (now - last)
                if wait > 0:
                    time.sleep(wait)
                last = time.time()
                self._last_view_ts = last

                with self._frame_lock:
                    base = None if self._latest is None else self._latest.copy()
                    anns = list(self._annotations)
                if base is None:
                    base = _placeholder()

                for a in anns:
                    x, y, bw, bh = a["box"]
                    cv2.rectangle(base, (x, y), (x + bw, y + bh), a["color"], 2)
                    cv2.putText(base, a["label"], (x, max(0, y - 8)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, a["color"], 2)

                ok, buf = cv2.imencode('.jpg', base, enc)
                if not ok:
                    continue
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + buf.tobytes() + b'\r\n')
        finally:
            self.remove_viewer()


@stream_bp.route('/feed')
@admin_required
def video_feed():
    mgr = StreamManager.instance(current_app._get_current_object())
    return Response(mgr.frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')


@stream_bp.route('/status')
@admin_required
def stream_status():
    mgr = StreamManager.instance(current_app._get_current_object())
    return jsonify(status=mgr._status, viewers=mgr._viewers,
                   cached_cases=len(mgr._emb_cache), source=mgr.current_source()), 200


@stream_bp.route('/source', methods=['GET'])
@admin_required
def get_source():
    mgr = StreamManager.instance(current_app._get_current_object())
    return jsonify(source=mgr.current_source()), 200


@stream_bp.route('/source', methods=['POST'])
@admin_required
def set_source():
    data = request.get_json(silent=True) or {}
    normalized = _normalize_source(data.get('source', ''))
    if normalized is None:
        return jsonify(msg="Source must be a webcam index (e.g. 0) or an "
                           "rtsp:// / http(s):// IP-camera URL"), 400
    mgr = StreamManager.instance(current_app._get_current_object())
    mgr.set_source(normalized)
    audit_logger().info("STREAM_SOURCE_SET source=%s by=%s",
                        normalized, get_jwt_identity())
    return jsonify(msg="Camera source updated", source=mgr.current_source()), 200
