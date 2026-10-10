from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, chat, documents
from app.database import Base, engine

app = FastAPI(
    title="Document Intelligence System",
    description="AI-powered document analysis with RAG.",
    version="1.1.0",
)

# Importing the routers imports the SQLAlchemy models before table creation.
Base.metadata.create_all(bind=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
