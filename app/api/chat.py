from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
import numpy as np
from app.database import get_db
from app.models.document_chunk import DocumentChunk
from app.models.document import Document
from app.services.embeddings import generate_single_embedding
from app.services.llm import generate_answer

router = APIRouter()  # ✅ Remove prefix here


class QuestionRequest(BaseModel):
    question: str
    document_id: str
    top_k: int = 3


class AnswerResponse(BaseModel):
    answer: str
    sources: list[dict]


def cosine_similarity(a, b):
    """Calculate cosine similarity between two 1D vectors"""
    a = np.array(a)
    b = np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


@router.post("/ask")  # ✅ Just /ask, not /chat/ask
async def ask_question(
    request: QuestionRequest,
    db: Session = Depends(get_db)
):
    """Ask a question about a document"""
    # Verify document exists
    document = db.query(Document).filter(Document.id == request.document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Generate question embedding
    question_embedding = generate_single_embedding(request.question)

    # Get all chunks for this document
    chunks = db.query(DocumentChunk).filter(
        DocumentChunk.document_id == request.document_id
    ).all()

    if not chunks:
        raise HTTPException(status_code=404, detail="No chunks found for this document")

    # Calculate similarities
    similarities = []
    for chunk in chunks:
        chunk_emb = chunk.get_embedding()
        similarity = cosine_similarity(question_embedding, chunk_emb)
        similarities.append({
            "chunk": chunk,
            "similarity": float(similarity)
        })

    # Sort by similarity and get top k
    similarities.sort(key=lambda x: x["similarity"], reverse=True)
    top_chunks = similarities[:request.top_k]

    # Build context from top chunks
    context = "\n\n".join([item["chunk"].chunk_text for item in top_chunks])

    # Generate answer
    try:
        answer = generate_answer(request.question, context)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Return formatted response
    return {
        "answer": answer,
        "document_name": document.filename,
        "sources": [
            {
                "chunk_index": item["chunk"].chunk_index,
                "similarity_score": item["similarity"],
                "preview": item["chunk"].chunk_text[:200] + "..."
            }
            for item in top_chunks
        ],
        "metadata": {
            "chunks_searched": len(chunks),
            "top_k_used": request.top_k,
            "model": "gemini-2.5-flash"
        }
    }