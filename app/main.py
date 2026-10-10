from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, chat, documents
from app.config import settings
from app.database import Base, engine

app = FastAPI(
    title="Document Intelligence System",
    description="AI-powered document analysis with retrieval-augmented generation.",
    version="1.1.0",
)

# Ensure model modules have been imported via app.api before creating tables.
Base.metadata.create_all(bind=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


app.include_router(auth.router, prefix="/auth")
app.include_router(documents.router, prefix="/documents")
app.include_router(chat.router, prefix="/chat")


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
