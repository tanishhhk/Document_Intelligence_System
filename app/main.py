from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api import auth, chat, documents, videos
from app.config import settings
from app.database import SessionLocal, engine, run_migrations, schema_is_current
from app.logging_config import configure_logging
from app.middleware.body_limit import BodySizeLimitMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_context import RequestContextMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.services.auth import token_user_id
from app.services.ingestion import IngestionWorker
from app.services.llm import configured_providers
from app.services.video_jobs import VideoWorker

configure_logging(settings.log_level, settings.log_format)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auto_migrate:
        run_migrations()
    worker = video_worker = None
    if settings.ingestion_worker_enabled:
        worker = IngestionWorker(SessionLocal, settings.upload_dir)
        worker.start()
        video_worker = VideoWorker(SessionLocal)
        video_worker.start()
    app.state.ingestion_worker = worker
    app.state.video_worker = video_worker
    yield
    for running in (worker, video_worker):
        if running is not None:
            running.stop()
    engine.dispose()


def docs_urls(enabled: bool) -> dict:
    if enabled:
        return {}
    return {"docs_url": None, "redoc_url": None, "openapi_url": None}


app = FastAPI(
    title="guruKool",
    description="AI-powered document analysis with RAG.",
    version="1.2.0",
    lifespan=lifespan,
    **docs_urls(settings.api_docs_enabled),
)

# Middleware added last runs first. CORS is outermost so browsers can read
# 429 and 413 responses, and preflight requests do not count toward limits.
app.add_middleware(BodySizeLimitMiddleware, settings=settings)
app.add_middleware(RateLimitMiddleware, settings=settings, token_subject=token_user_id)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "Accept"],
    max_age=600,
)
# Outermost, so every response, including 413 and 429, has a request ID.
app.add_middleware(RequestContextMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(documents.router, prefix="/documents", tags=["Documents"])
app.include_router(chat.router, prefix="/chat", tags=["Chat"])
app.include_router(videos.router, prefix="/videos", tags=["Stories and videos"])


@app.get("/")
def root():
    return {
        "message": "guruKool API",
        "status": "running",
        "version": app.version,
    }


@app.get("/health")
def health_check():
    """Liveness: the process is running and serving requests."""
    return {"status": "ok"}


@app.get("/ready")
def readiness_check():
    """Readiness: the database is reachable and migrated, and the worker runs if enabled."""
    checks = {}
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            checks["database"] = "ok"
            checks["schema"] = "current" if schema_is_current(connection) else "outdated"
    except Exception:
        checks["database"] = "unavailable"

    # Informational: with no provider, questions get the extractive fallback.
    checks["answer_providers"] = [p.name for p in configured_providers()] or "none"

    for name in ("ingestion_worker", "video_worker"):
        worker = getattr(app.state, name, None)
        if not settings.ingestion_worker_enabled:
            checks[name] = "disabled"
        else:
            checks[name] = "running" if worker and worker.is_alive() else "stopped"
    checks["video_rendering"] = "enabled" if settings.video_render_enabled else "disabled"

    ready = (
        checks["database"] == "ok"
        and checks.get("schema") == "current"
        and "stopped" not in (checks["ingestion_worker"], checks["video_worker"])
    )
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ready" if ready else "not_ready", "checks": checks},
    )
