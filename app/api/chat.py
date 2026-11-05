import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.config import settings
from app.database import get_db
from app.models.document import Document
from app.models.user import User
from app.services import ingestion
from app.services.embeddings import generate_single_embedding
from app.services.llm import NOT_FOUND_ANSWER, cited_source_ids, generate_answer
from app.services.retrieval import retrieve

logger = logging.getLogger(__name__)
router = APIRouter()


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    document_id: str = Field(min_length=1, max_length=128)
    top_k: int = Field(default=3, ge=1, le=10)


@router.post("/ask")
def ask_question(
    request: QuestionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Answer a question using only a document owned by the current user."""
    question = request.question.strip()
    if not question:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Question cannot be blank.",
        )

    document = (
        db.query(Document)
        .filter(
            Document.id == request.document_id,
            Document.user_id == current_user.id,
        )
        .first()
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    if document.status in (ingestion.QUEUED, ingestion.PROCESSING):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This document is still being processed. Try again shortly.",
        )
    if document.status == ingestion.FAILED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Processing failed for this document, so it cannot be searched. "
            "Retry processing or upload it again.",
        )

    result = retrieve(db, document.id, generate_single_embedding(question), request.top_k)
    if not result.chunks:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This document has no usable indexed text. Retry processing to index it again.",
        )

    try:
        raw_answer = generate_answer(question, result.chunks)
    except Exception as exc:
        logger.exception("Answer generation failed.")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The answer service is unavailable.",
        ) from exc

    answer, cited = cited_source_ids(raw_answer, result.chunks)
    found = bool(cited) or NOT_FOUND_ANSWER.lower() not in answer.lower()
    return {
        "answer": answer,
        "answer_status": "answered" if found else "not_found",
        "document_id": document.id,
        "document_name": document.filename,
        "sources": [
            {
                "source_id": chunk.source_id,
                "chunk_index": chunk.chunk_index,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "similarity_score": round(chunk.score, 6),
                "preview": chunk.text[:200],
                "cited": chunk.source_id in cited,
            }
            for chunk in result.chunks
        ],
        "metadata": {
            "chunks_searched": result.searched,
            "chunks_skipped": result.skipped,
            "top_k_used": len(result.chunks),
            "model": settings.gemini_model,
        },
    }
