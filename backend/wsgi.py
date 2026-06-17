"""
Production entry point. Serves the app with Waitress (a production-grade WSGI
server that runs natively on Windows).

    cd backend
    set APP_ENV=production
    python wsgi.py            # serves on 0.0.0.0:5000

Environment variables of note (see .env.example):
    APP_ENV, SECRET_KEY, JWT_SECRET_KEY, ADMIN_PASSWORD, CORS_ORIGINS,
    CAMERA_SOURCE, HOST, PORT, THREADS
"""

import os

from waitress import serve

from app import create_app

app = create_app(os.environ.get("APP_ENV", "production"))

if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5000"))
    threads = int(os.environ.get("THREADS", "8"))
    app.logger.info("Starting Waitress on %s:%s (threads=%s)", host, port, threads)
    serve(app, host=host, port=port, threads=threads)
