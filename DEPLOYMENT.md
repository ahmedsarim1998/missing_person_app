# locAIte — Deployment Guide

AI-powered missing-person identification platform. A single Flask application
serves both the REST API (`/api/*`) and the static frontend (`new_front_end/`).
In production it runs behind **Waitress**, a production-grade WSGI server.

---

## 1. Prerequisites

- Python 3.7+ (developed and tested on 3.7.9, Windows 11)
- A webcam on the host if you want the live surveillance stream (optional)
- ~2 GB free disk for the TensorFlow / FaceNet model weights

## 2. Install

```bat
cd backend
pip install -r requirements.txt
:: optional, improves location extraction accuracy:
python -m spacy download en_core_web_sm
```

## 3. Configure

Copy the template and edit values:

```bat
copy .env.example backend\.env
```

Key settings (all optional — safe defaults are applied):

| Variable | Purpose | Default |
|----------|---------|---------|
| `APP_ENV` | `development` / `production` / `testing` | `production` |
| `SECRET_KEY`, `JWT_SECRET_KEY` | App/JWT secrets. Auto-generated & persisted to `backend/instance/*.key` if unset. | random |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | Seed admin. If password unset, a random one is generated and printed to the log **once** on first boot. | `admin` / random |
| `CORS_ORIGINS` | Comma-separated allowed origins | localhost:5000 |
| `CAMERA_SOURCE` | `0` = webcam, or an RTSP/HTTP URL | `0` |
| `HOST` / `PORT` / `THREADS` | Waitress bind + worker threads | `0.0.0.0` / `5000` / `8` |
| `LOGIN_MAX_ATTEMPTS` / `LOGIN_WINDOW_SECONDS` | Login throttle | `10` / `300` |
| `MAX_CONTENT_LENGTH_MB` | Max upload size | `25` |
| `LOG_LEVEL` | `INFO` / `DEBUG` / `WARNING` | `INFO` |

## 4. Run

**Production (recommended):**
```bat
run_prod.bat
:: or manually:
cd backend && set APP_ENV=production && python wsgi.py
```

**Development (Flask dev server, auto-reload):**
```bat
run_app.bat
```

Open **http://localhost:5000**. On first boot, watch the console for the seeded
admin password if you did not set `ADMIN_PASSWORD`.

## 5. First-login / admin password

```bat
cd backend
python reset_admin.py --password "YourStrongPassword"
```

## 6. Optional: live social-media scan loop

Configure `FB_GROUP` / `FB_COOKIES` in `.env`, then:
```bat
cd backend && python fb_scan_runner.py --interval 600      # live
cd backend && python fb_scan_runner.py --once --demo       # one demo pass
```

## 7. Run the test suite

```bat
cd backend
python -m pytest
```
The suite (auth, RBAC, cases, admin audit trail, analyzer) runs offline and does
**not** load TensorFlow.

---

## Security summary

- **JWT auth on every protected route**; role-based access control (`admin` vs `user`)
  enforced server-side via `security.role_required`.
- Passwords hashed with Werkzeug (PBKDF2). Public signup cannot self-assign admin.
- Secrets are never hard-coded — read from env or auto-generated and persisted
  outside source control (`backend/instance/*.key`, git-ignored).
- Login throttling (sliding window) returns `429` after repeated failures.
- Upload validation: extension allow-list + max size; filenames sanitised; path
  traversal blocked on the static frontend route.
- Security headers (`X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`, `X-XSS-Protection`) and `Cache-Control: no-store` on the API.
- CORS restricted to configured origins.
- The live stream is admin-only; its `<img>` tag authenticates via a short-lived
  `?jwt=` query token.

## Logging & audit

- Rotating logs in `backend/logs/`:
  - `app.log` — application + errors
  - `audit.log` — security events: logins (ok/fail/blocked), signups, case
    create/status changes, match confirm/reject (**who + when**), FB scans.

## Data & operations

- SQLite DB at `backend/instance/missing_persons.db` (override via `DATABASE_URL`).
- Uploaded photos and live-match snapshots under `backend/static/uploads/`.
- Match alerts are de-duplicated with a 30-second per-person cooldown and store a
  cropped live snapshot for side-by-side admin review.
