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
from app.services.llm import (
    NOT_FOUND_ANSWER,
    AnswerServiceError,
    extractive_answer,
    cited_source_ids,
    generate_answer,
)
from app.services.retrieval import retrieve

logger = logging.getLogger(__name__)
router = APIRouter()


# Status, message and default Retry-After for each AnswerServiceError kind.
_ANSWER_SERVICE_ERRORS = {
    "timeout": (
        status.HTTP_504_GATEWAY_TIMEOUT,
        "The answer service took too long to respond. Try again.",
        5,
    ),
    "busy": (
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "The answer service is busy or has reached its usage limit. Try again later.",
        30,
    ),
    "unavailable": (
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "The answer service is temporarily unavailable. Try again shortly.",
        10,
    ),
    "misconfigured": (
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "The answer service is not configured correctly. Contact the administrator.",
        None,
    ),
    "rejected": (
        status.HTTP_502_BAD_GATEWAY,
        "The answer service could not answer this question. Try rephrasing it.",
        None,
    ),
    "empty": (
        status.HTTP_502_BAD_GATEWAY,
        "The answer service returned an empty answer. Try rephrasing the question.",
        None,
    ),
}


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

    fallback_reason = None
    try:
        generated = generate_answer(question, result.chunks)
    except AnswerServiceError as exc:
        logger.warning("Answer generation failed.", extra={"kind": exc.kind})
        if settings.answer_fallback != "extractive":
            status_code, detail, default_retry = _ANSWER_SERVICE_ERRORS[exc.kind]
            retry_after = exc.retry_after or default_retry
            raise HTTPException(
                status_code=status_code,
                detail=detail,
                headers={"Retry-After": str(max(1, round(retry_after)))} if retry_after else None,
            ) from exc
        generated = None
        fallback_reason = exc.kind

    if generated is None:
        answer, cited = extractive_answer(result.chunks)
        answer_status = "extractive"
    else:
        answer, cited = cited_source_ids(generated.text, result.chunks)
        found = bool(cited) or NOT_FOUND_ANSWER.lower() not in answer.lower()
        answer_status = "answered" if found else "not_found"
    return {
        "answer": answer,
        "answer_status": answer_status,
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
            "provider": generated.provider if generated else None,
            "model": generated.model if generated else None,
            "fallback_reason": fallback_reason,
        },
    }
