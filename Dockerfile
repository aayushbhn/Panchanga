# Panchanga API - Production image for Coolify
FROM python:3.12-slim

# WeasyPrint (flask_weasyprint) system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Application code and ephemeris data
COPY api.py .
# COPY constants.py .
COPY de421.bsp .
COPY templates/ templates/

# Gunicorn: bind to 0.0.0.0 so Coolify can reach it; use PORT if set (Coolify often sets this)
ENV PORT=5000
EXPOSE 5000

# Workers/threads are env-tunable (defaults match prior behavior: 2 workers, 4
# threads). Bump WEB_CONCURRENCY toward your vCPU count for more parallel
# CPU-bound requests; threads help overlap the blocking kundali/mantra calls.
# NOTE: do not add --preload — each worker imports independently so its own
# background prewarm thread pool starts cleanly (ThreadPoolExecutor is not
# fork-safe).
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT} --workers ${WEB_CONCURRENCY:-2} --threads ${GUNICORN_THREADS:-4} --timeout 120 api:app"]
