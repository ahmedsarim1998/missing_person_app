# locAIte — container image for cloud deployment (Render, Railway, Fly, etc.)
# Pins Python 3.10 because TensorFlow 2.11 has no wheels for 3.11+, and most
# managed platforms no longer offer the project's original 3.7 runtime.
FROM python:3.10-slim

# OpenCV (headless) still needs a couple of shared libs at runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first so Docker can cache this layer.
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# App source.
COPY . .

ENV APP_ENV=production \
    HOST=0.0.0.0 \
    PYTHONUNBUFFERED=1

WORKDIR /app/backend

# The platform injects $PORT; wsgi.py reads it (defaults to 5000 locally).
EXPOSE 5000
CMD ["python", "wsgi.py"]
