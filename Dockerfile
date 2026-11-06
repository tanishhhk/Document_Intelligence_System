FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FASTEMBED_CACHE_PATH=/opt/models

WORKDIR /app
RUN groupadd --system --gid 1000 app && useradd --system --uid 1000 --gid app --home-dir /app --no-create-home app

# A TrueType font for video slides; the default bitmap font is unreadably small.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

# Include the embedding and re-ranking models (ONNX, run by fastembed) so
# containers start without downloading them.
RUN python -c "from fastembed import TextEmbedding; from fastembed.rerank.cross_encoder import TextCrossEncoder; TextEmbedding('sentence-transformers/all-MiniLM-L6-v2', cache_dir='/opt/models'); TextCrossEncoder('Xenova/ms-marco-MiniLM-L-6-v2', cache_dir='/opt/models')" \
    && chmod -R a+rX /opt/models

COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app
RUN mkdir -p /data/uploads /data/videos /data/db && chown app:app /data/uploads /data/videos /data/db

USER app
ENV UPLOAD_DIR=/data/uploads \
    VIDEO_DIR=/data/videos \
    HF_HUB_OFFLINE=1
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os, sys, urllib.request; sys.exit(urllib.request.urlopen(f\"http://127.0.0.1:{os.environ.get('PORT', '8000')}/health\", timeout=4).status != 200)"

# PORT is set by hosts such as Render. FORWARDED_ALLOW_IPS lists the reverse
# proxies whose X-Forwarded-For is trusted.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"${PORT:-8000}\" --proxy-headers --forwarded-allow-ips=\"${FORWARDED_ALLOW_IPS:-127.0.0.1}\" --timeout-graceful-shutdown 30"]
