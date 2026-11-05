import json
import logging
import re
from dataclasses import dataclass

import numpy as np
from sqlalchemy.orm import Session

from app.models.document_chunk import DocumentChunk
from app.services.embeddings import EMBEDDING_DIMENSION, EMBEDDING_MODEL
from app.services.ranking import rank
from app.services.reranker import rerank

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetrievedChunk:
    source_id: str
    chunk_index: int
    text: str
    page_start: int | None
    page_end: int | None
    score: float


@dataclass(frozen=True)
class RetrievalResult:
    chunks: list[RetrievedChunk]
    searched: int
    skipped: int


def _usable_vector(raw: str):
    try:
        vector = np.asarray(json.loads(raw), dtype=np.float32)
    except (TypeError, ValueError):
        return None
    if vector.shape != (EMBEDDING_DIMENSION,) or not np.isfinite(vector).all():
        return None
    norm = float(np.linalg.norm(vector))
    return vector / norm if norm > 0 else None


def _dedupe_key(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def retrieve(
    db: Session, document_id: str, question_vector, top_k: int, question: str | None = None
) -> RetrievalResult:
    """Rank a document's chunks for the question.

    With the question text, embedding similarity is fused with BM25 keyword
    scores and the top candidates are re-ranked (app.services.ranking);
    without it, chunks are ranked by cosine similarity alone.

    The caller must already have checked that the document belongs to the
    current user. Chunks embedded by a different model, or with vectors that
    are malformed, the wrong size, non-finite or zero, are skipped.
    """
    rows = (
        db.query(
            DocumentChunk.chunk_index,
            DocumentChunk.chunk_text,
            DocumentChunk.embedding,
            DocumentChunk.page_start,
            DocumentChunk.page_end,
            DocumentChunk.embedding_model,
        )
        .filter(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
        .all()
    )

    usable, vectors = [], []
    for row in rows:
        vector = _usable_vector(row.embedding) if row.embedding_model == EMBEDDING_MODEL else None
        if vector is not None:
            usable.append(row)
            vectors.append(vector)
    skipped = len(rows) - len(usable)
    if skipped:
        logger.warning(
            "Skipped unusable chunk embeddings.",
            extra={"document_id": document_id, "skipped": skipped},
        )
    if not usable:
        return RetrievalResult([], searched=len(rows), skipped=skipped)

    query = np.asarray(question_vector, dtype=np.float32)
    query = query / np.linalg.norm(query)
    scores = np.vstack(vectors) @ query

    selected, seen = [], set()
    if question:
        order = rank(question, [row.chunk_text for row in usable], scores, rerank)
    else:
        order = np.argsort(-scores, kind="stable")
    for index in order:
        row = usable[index]
        key = _dedupe_key(row.chunk_text)
        if key in seen:
            continue
        seen.add(key)
        selected.append(
            RetrievedChunk(
                source_id=f"S{len(selected) + 1}",
                chunk_index=row.chunk_index,
                text=row.chunk_text,
                page_start=row.page_start,
                page_end=row.page_end,
                score=float(scores[index]),
            )
        )
        if len(selected) == top_k:
            break
    return RetrievalResult(selected, searched=len(rows), skipped=skipped)
