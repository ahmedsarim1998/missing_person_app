# locAIte — AI-Powered Missing-Person Identification Platform

locAIte is a full-stack web platform that helps locate missing people using facial
recognition. Cases are reported with photos, and a live video feed (webcam or
RTSP/HTTP camera) is continuously scanned in real time, matching detected faces
against the database of active cases. Administrators review and confirm matches
through a dedicated dashboard.

A single Flask application serves both the REST API (`/api/*`) and the static
frontend. In production it runs behind **Waitress**, a production-grade WSGI server.

---

## Features

- **Case reporting** — submit a missing person with photos, national ID, last
  known location, and identifying marks.
- **Facial recognition engine** — MTCNN for face detection and FaceNet for
  128-dimensional embeddings, matched by Euclidean distance.
- **Live surveillance stream** — real-time MJPEG feed with on-frame match boxes,
  decoupled multi-viewer playback, and an idle-timeout camera release.
- **Admin dashboard** — side-by-side review of live matches vs. stored photos,
  confirm/reject alerts, and case management.
- **Authentication & RBAC** — JWT auth with `admin` / `user` roles enforced
  server-side; public signup cannot self-assign admin.
- **Audit logging** — security events (logins, signups, case changes, match
  decisions) recorded to a rotating `audit.log`.
- **Optional social-media analyzer** — fuzzy-name + NER pipeline that can scan an
  external source (falls back gracefully when dependencies are absent).

## Tech Stack

| Layer | Technologies |
|-------|--------------|
| Backend | Python, Flask, Flask-SQLAlchemy, Flask-JWT-Extended, Waitress |
| Database | SQLite (via SQLAlchemy ORM) |
| AI / CV | TensorFlow, keras-facenet, MTCNN, OpenCV, NumPy/SciPy |
| Frontend | Static HTML / CSS / JavaScript (served by Flask) |
| Analyzer | rapidfuzz, spaCy, facebook-scraper (optional) |

## Project Structure

```
.
├── backend/              # Flask application (API + AI engine)
│   ├── app.py            # App factory, blueprints, security headers
│   ├── wsgi.py           # Production entrypoint (Waitress)
│   ├── config.py         # Env-driven configuration
│   ├── models.py         # SQLAlchemy models: User, MissingPerson, MatchAlert
│   ├── routes/           # auth, cases, admin, stream, fb blueprints
│   ├── utils/            # face_recognition + social-media analyzer
│   └── tests/            # pytest suite (runs offline, no TensorFlow)
├── new_front_end/        # Static HTML/CSS/JS frontend (served by Flask)
├── diagrams/             # Architecture, ERD, use-case, flowchart images
├── .env.example          # Configuration template
├── DEPLOYMENT.md         # Full deployment & operations guide
└── project_summary.md    # Technical summary (architecture, schema, data flow)
```

## Quick Start

> Requires Python 3.7+ and ~2 GB free disk for the TensorFlow / FaceNet weights.
> A webcam on the host is optional (only needed for the live stream).

```bash
# 1. Install dependencies
cd backend
pip install -r requirements.txt
python -m spacy download en_core_web_sm   # optional, improves location extraction

# 2. Configure (all values are optional — safe defaults are applied)
cp ../.env.example .env

# 3. Run
python wsgi.py            # production (Waitress)
# or, for development with auto-reload:
python app.py
```

Then open **http://localhost:5000**. On first boot, if you didn't set
`ADMIN_PASSWORD`, watch the console for the auto-generated admin password (change
it immediately).

On Windows you can use the provided helper scripts: `run_prod.bat` /  `run_app.bat`.

For the full configuration reference, security notes, and operational details, see
**[DEPLOYMENT.md](DEPLOYMENT.md)**.

## Configuration

All settings are read from environment variables (or `backend/.env`). Secrets are
auto-generated and persisted to `backend/instance/` if not provided, so the app
runs out of the box. Key variables:

| Variable | Purpose | Default |
|----------|---------|---------|
| `APP_ENV` | `development` / `production` / `testing` | `production` |
| `SECRET_KEY`, `JWT_SECRET_KEY` | App/JWT secrets (auto-generated if unset) | random |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | Seed admin account | `admin` / random |
| `CAMERA_SOURCE` | `0` = webcam, or an RTSP/HTTP URL | `0` |
| `MATCH_THRESHOLD` | Face-match distance threshold (lower = stricter) | `0.65` |
| `HOST` / `PORT` / `THREADS` | Waitress bind + worker threads | `0.0.0.0` / `5000` / `8` |

See [.env.example](.env.example) for the complete list.

## Testing

```bash
cd backend
python -m pytest
```

The suite covers auth, RBAC, cases, the admin audit trail, and the analyzer. It
runs fully offline and does **not** load TensorFlow.

## Security Highlights

- JWT auth on every protected route; role-based access control enforced server-side.
- Passwords hashed with Werkzeug (PBKDF2).
- Secrets never hard-coded — read from env or auto-generated outside source control.
- Login throttling (sliding window) returns `429` after repeated failures.
- Upload validation (extension allow-list + size cap), filename sanitisation, and
  path-traversal protection on the static routes.
- Security headers and CORS restricted to configured origins.

## License

This project was developed as a final-year project. Add a license here before
distributing publicly.
