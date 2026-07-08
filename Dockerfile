# locAIte — container image for cloud deployment (Render, Railway, Fly, etc.)
# Pins Python 3.10 because TensorFlow 2.11 has no wheels for 3.11+, and most
# managed platforms no longer offer the project's original 3.7 runtime.
FROM python:3.10-slim

# OpenCV needs a few shared libs at runtime (libgl1 for cv2, plus glib/gomp).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first so Docker can cache this layer. Uses the trimmed,
# 3.10-pinned deploy list (the full requirements.txt targets Python 3.7 and its
# optional analyzer deps conflict on newer Pythons).
COPY backend/requirements-deploy.txt ./backend/requirements-deploy.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r backend/requirements-deploy.txt

# App source.
COPY . .

ENV APP_ENV=production \
    HOST=0.0.0.0 \
    PYTHONUNBUFFERED=1

WORKDIR /app/backend

# The platform injects $PORT; wsgi.py reads it (defaults to 5000 locally).
EXPOSE 5000
CMD ["python", "wsgi.py"]
