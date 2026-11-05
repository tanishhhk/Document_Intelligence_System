from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, chat, documents
from app.config import settings
from app.database import run_migrations
from app.middleware.body_limit import BodySizeLimitMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.services.auth import token_user_id


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.auto_migrate:
        run_migrations()
    yield


app = FastAPI(
    title="Document Intelligence System",
    description="AI-powered document analysis with RAG.",
    version="1.2.0",
    lifespan=lifespan,
)

# Middleware added last runs first. CORS is outermost so browsers can read
# 429 and 413 responses, and preflight requests do not count toward limits.
app.add_middleware(BodySizeLimitMiddleware, settings=settings)
app.add_middleware(RateLimitMiddleware, settings=settings, token_subject=token_user_id)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "Accept"],
    max_age=600,
)

app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(documents.router, prefix="/documents", tags=["Documents"])
app.include_router(chat.router, prefix="/chat", tags=["Chat"])


@app.get("/")
def root():
    return {
        "message": "Document Intelligence System API",
        "status": "running",
        "version": app.version,
    }


@app.get("/health")
def health_check():
    return {"status": "ok"}
