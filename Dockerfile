# =============================================================================
#  Dockerfile — Sarathi-AI Business Technologies
# =============================================================================
#  Multi-tenant CRM SaaS. SQLite stored in Docker volume for persistence.
#  Build:  docker build -t sarathi-ai .
#  Run:    docker compose up -d
# =============================================================================

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# System deps for potential native packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev && rm -rf /var/lib/apt/lists/*

# Install Python deps first (Docker layer caching)
COPY biz_requirements.txt .
RUN pip install --no-cache-dir -r biz_requirements.txt

# Copy all application code
COPY *.py ./
COPY biz.env ./
COPY static/ ./static/

# Create directories for runtime data
RUN mkdir -p /app/generated_pdfs /app/gdrive_tokens

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import httpx; r = httpx.get('http://localhost:8001/health'); assert r.status_code == 200"

# Port for FastAPI
EXPOSE 8001

# Run Sarathi
CMD ["python", "sarathi_biz.py"]
