from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base
from app.api import auth, documents, chat

# Initialize FastAPI app
app = FastAPI(
    title="Document Intelligence System",
    description="AI-powered document analysis with RAG",
    version="1.0.0"
)

# Create all database tables
Base.metadata.create_all(bind=engine)

# CORS middleware (allows frontend to talk to backend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers with prefixes
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(documents.router, prefix="/documents", tags=["Documents"])
app.include_router(chat.router, prefix="/chat", tags=["Chat"])  # ✅ Prefix added here

@app.get("/")
async def root():
    return {
        "message": "Document Intelligence System API",
        "status": "running",
        "version": "1.0.0"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}