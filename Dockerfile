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

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT} --workers 2 --threads 4 --timeout 120 api:app"]
