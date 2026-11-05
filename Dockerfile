FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/models

WORKDIR /app
# UID 1000 is the user Hugging Face Spaces runs containers as.
RUN groupadd --system --gid 1000 app && useradd --system --uid 1000 --gid app --home-dir /app --no-create-home app

# A TrueType font for video slides; the default bitmap font is unreadably small.
RUN apt-get update     && apt-get install -y --no-install-recommends fonts-dejavu-core     && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# The CPU build of torch is much smaller than the default CUDA build.
RUN pip install torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu \
    && pip install -r requirements.txt

# Include the embedding and re-ranking models so containers start without downloading them.
RUN python -c "from sentence_transformers import CrossEncoder, SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2'); CrossEncoder('cross-encoder/ms-marco-MiniLM-L6-v2')" \
    && chmod -R a+rX /opt/models

COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app
RUN mkdir -p /data/uploads /data/videos /data/db && chown app:app /data/uploads /data/videos /data/db

USER app
ENV UPLOAD_DIR=/data/uploads     VIDEO_DIR=/data/videos \
    HF_HUB_OFFLINE=1
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import sys, urllib.request; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status != 200)"

# FORWARDED_ALLOW_IPS lists the reverse proxies whose X-Forwarded-For is trusted.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips=\"${FORWARDED_ALLOW_IPS:-127.0.0.1}\" --timeout-graceful-shutdown 30"]
