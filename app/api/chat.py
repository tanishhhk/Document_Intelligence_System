import logging

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.config import settings
from app.database import get_db
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.user import User
from app.services.embeddings import generate_single_embedding
from app.services.llm import generate_answer

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Chat"])


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    document_id: str = Field(min_length=1)
    top_k: int = Field(default=3, ge=1, le=10)


def cosine_similarity(a, b) -> float:
    """Compute cosine similarity safely for two embedding vectors."""
    vector_a = np.asarray(a, dtype=np.float32)
    vector_b = np.asarray(b, dtype=np.float32)
    if vector_a.shape != vector_b.shape or vector_a.ndim != 1:
        return 0.0
    denominator = float(np.linalg.norm(vector_a) * np.linalg.norm(vector_b))
    if denominator == 0.0:
        return 0.0
    return float(np.dot(vector_a, vector_b) / denominator)


@router.post("/ask")
def ask_question(
    request: QuestionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Answer a question using only a document owned by the authenticated user."""
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Question cannot be blank.")

    document = (
        db.query(Document)
        .filter(Document.id == request.document_id, Document.user_id == current_user.id)
        .first()
    )
    if document is None:
        # Do not reveal whether another account owns this document.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document.id)
        .order_by(DocumentChunk.chunk_index)
        .all()
    )
    if not chunks:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This document has no indexed text available for questions.",
        )

    question_embedding = generate_single_embedding(question)
    ranked_chunks = []
    for chunk in chunks:
        similarity = cosine_similarity(question_embedding, chunk.get_embedding())
        ranked_chunks.append({"chunk": chunk, "similarity": similarity})
    ranked_chunks.sort(key=lambda item: item["similarity"], reverse=True)
    top_chunks = ranked_chunks[: request.top_k]

    context = "\n\n".join(
        f"[Source chunk {item['chunk'].chunk_index}]\n{item['chunk'].chunk_text}"
        for item in top_chunks
    )
    try:
        answer = generate_answer(question, context)
    except Exception as exc:
        logger.exception("Answer generation failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The answer provider failed. Please retry shortly.",
        ) from exc

    return {
        "answer": answer,
        "document_name": document.filename,
        "sources": [
            {
                "chunk_index": item["chunk"].chunk_index,
                "similarity_score": round(item["similarity"], 6),
                "preview": (
                    item["chunk"].chunk_text[:200]
                    + ("..." if len(item["chunk"].chunk_text) > 200 else "")
                ),
            }
            for item in top_chunks
        ],
        "metadata": {
            "chunks_searched": len(chunks),
            "top_k_used": len(top_chunks),
            "model": settings.gemini_model,
        },
    }
