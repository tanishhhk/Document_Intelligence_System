from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, chat, documents
from app.config import settings
from app.database import Base, engine
from app.middleware.rate_limit import RateLimitMiddleware

app = FastAPI(
    title="Document Intelligence System",
    description="AI-powered document analysis with RAG.",
    version="1.2.0",
)

Base.metadata.create_all(bind=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware, settings=settings)

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
