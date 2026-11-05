"""Durable, database-backed processing of uploaded documents.

Each document row is its own job. Uploads create documents in the "queued"
state. A worker claims one by moving it to "processing" with a lease, then
extracts, chunks and embeds the PDF and stores the result in a single
transaction. A worker that dies leaves an expired lease behind, and the next
worker claims the document again. Completion is fenced by the lease token,
so a worker that lost its lease cannot overwrite another worker's result.
"""
import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import and_, or_
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.embeddings import EMBEDDING_DIMENSION, EMBEDDING_MODEL, generate_embeddings
from app.utils.pdf_processor import extract_pages
from app.utils.text_processor import chunk_pages

logger = logging.getLogger(__name__)

QUEUED = "queued"
PROCESSING = "processing"
COMPLETED = "completed"
FAILED = "failed"

MAX_ATTEMPTS = 3
LEASE_SECONDS = 15 * 60
POLL_SECONDS = 2.0
ORPHAN_FILE_AGE_SECONDS = 60 * 60
ORPHAN_SWEEP_SECONDS = 60 * 60
_ERROR_MESSAGE_LIMIT = 500


class DocumentRejected(ValueError):
    """The file cannot be processed as uploaded; retrying will not help."""


def extract_and_embed_pdf(pdf_bytes: bytes):
    """Extract, chunk and embed a bounded amount of PDF text.

    Returns (chunks, embeddings, page_count).
    """
    try:
        pages = extract_pages(
            pdf_bytes,
            max_pages=settings.max_pdf_pages,
            max_chars=settings.max_pdf_chars,
        )
    except ValueError as exc:
        raise DocumentRejected(str(exc)) from exc
    except Exception as exc:
        raise DocumentRejected(
            "The PDF could not be read. Check that it is a valid, unencrypted PDF."
        ) from exc

    if not any(text.strip() for _number, text in pages):
        raise DocumentRejected("No selectable text was found. Scanned PDFs need OCR.")

    chunks = chunk_pages(pages)
    if not chunks:
        raise DocumentRejected("The PDF did not produce any text chunks.")

    started = time.monotonic()
    embeddings = generate_embeddings([chunk.text for chunk in chunks])
    logger.info(
        "Embedded chunks.",
        extra={"chunk_count": len(chunks), "duration_ms": round((time.monotonic() - started) * 1000)},
    )
    return chunks, embeddings, len(pages)


def _claimable(now: int):
    return or_(
        Document.status == QUEUED,
        and_(
            Document.status == PROCESSING,
            or_(Document.lease_expires_at.is_(None), Document.lease_expires_at <= now),
        ),
    )


def claim_next_document(session_factory):
    """Claim the oldest queued or abandoned document. Returns (id, token) or None."""
    with session_factory() as db:
        for _ in range(5):
            now = int(time.time())
            candidate = (
                db.query(Document.id)
                .filter(_claimable(now))
                .order_by(Document.upload_date)
                .limit(1)
                .scalar()
            )
            if candidate is None:
                return None

            token = str(uuid.uuid4())
            claimed = (
                db.query(Document)
                .filter(Document.id == candidate, _claimable(now))
                .update(
                    {
                        Document.status: PROCESSING,
                        Document.lease_token: token,
                        Document.lease_expires_at: now + LEASE_SECONDS,
                        Document.attempts: Document.attempts + 1,
                    },
                    synchronize_session=False,
                )
            )
            db.commit()
            if claimed == 1:
                return candidate, token
            # Another worker claimed it first; look for the next one.
    return None


def _finish(db, document_id, token, values) -> bool:
    updated = (
        db.query(Document)
        .filter(Document.id == document_id, Document.lease_token == token)
        .update(
            {**values, Document.lease_token: None, Document.lease_expires_at: None},
            synchronize_session=False,
        )
    )
    return updated == 1


def _record_failure(session_factory, document_id, token, message, attempts):
    retry = message is None and attempts < MAX_ATTEMPTS
    values = {
        Document.status: QUEUED if retry else FAILED,
        Document.error_message: (
            message or "The document could not be processed. Retry later."
        )[:_ERROR_MESSAGE_LIMIT],
    }
    with session_factory() as db:
        if _finish(db, document_id, token, values):
            db.commit()


def process_document(session_factory, document_id: str, token: str) -> None:
    """Process one claimed document. Never raises for document-level failures."""
    started = time.monotonic()
    with session_factory() as db:
        document = db.get(Document, document_id)
        if document is None or document.lease_token != token:
            return
        file_path, attempts = document.file_path, document.attempts

    if attempts > MAX_ATTEMPTS:
        # Earlier attempts never reported back, for example because parsing
        # this file crashed the worker. Do not parse it again.
        _record_failure(
            session_factory,
            document_id,
            token,
            "Processing stopped repeatedly before finishing. The file may be malformed.",
            attempts,
        )
        return

    try:
        # Read into memory so the file is not held open while it is parsed,
        # which would stop a concurrent delete from removing it on Windows.
        pdf_bytes = Path(file_path).read_bytes()
    except FileNotFoundError:
        _record_failure(
            session_factory,
            document_id,
            token,
            "The uploaded file is no longer available. Upload it again.",
            attempts,
        )
        return

    try:
        chunks, embeddings, page_count = extract_and_embed_pdf(pdf_bytes)
    except DocumentRejected as exc:
        _record_failure(session_factory, document_id, token, str(exc), attempts)
        logger.info("Document rejected during processing.", extra={"document_id": document_id})
        return
    except Exception:
        logger.exception("Document processing failed.", extra={"document_id": document_id})
        _record_failure(session_factory, document_id, token, None, attempts)
        return

    with session_factory() as db:
        try:
            # Clear chunks from an earlier attempt so a re-run cannot duplicate them.
            db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete(
                synchronize_session=False
            )
            for index, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=True)):
                row = DocumentChunk(
                    id=str(uuid.uuid4()),
                    document_id=document_id,
                    chunk_index=index,
                    chunk_text=chunk.text,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                    embedding_model=EMBEDDING_MODEL,
                    embedding_dim=EMBEDDING_DIMENSION,
                )
                row.set_embedding(embedding)
                db.add(row)
            db.flush()
            owned = _finish(
                db,
                document_id,
                token,
                {
                    Document.status: COMPLETED,
                    Document.error_message: None,
                    Document.chunk_count: len(chunks),
                    Document.page_count: page_count,
                    Document.processed_at: datetime.now(timezone.utc).replace(tzinfo=None),
                },
            )
            if not owned:
                # Deleted, or claimed by another worker after our lease expired.
                db.rollback()
                return
            db.commit()
        except SQLAlchemyError:
            # Most often the document was deleted while it was being processed.
            db.rollback()
            logger.info("Discarded processing result.", extra={"document_id": document_id})
            return

    logger.info(
        "Document processed.",
        extra={
            "document_id": document_id,
            "chunk_count": len(chunks),
            "duration_ms": round((time.monotonic() - started) * 1000),
        },
    )


def process_pending(session_factory, limit: int | None = None) -> int:
    """Process queued documents until none are left. Returns how many were processed."""
    processed = 0
    while limit is None or processed < limit:
        claim = claim_next_document(session_factory)
        if claim is None:
            break
        process_document(session_factory, *claim)
        processed += 1
    return processed


def remove_orphan_files(session_factory, upload_dir: str, min_age_seconds: int = ORPHAN_FILE_AGE_SECONDS) -> int:
    """Delete stored PDFs with no document row, such as files left by a crash."""
    folder = Path(upload_dir)
    if not folder.is_dir():
        return 0
    cutoff = time.time() - min_age_seconds
    candidates = {
        path.stem: path
        for path in folder.glob("*.pdf")
        if path.is_file() and path.stat().st_mtime < cutoff
    }
    if not candidates:
        return 0
    with session_factory() as db:
        known = {
            row[0]
            for row in db.query(Document.id).filter(Document.id.in_(list(candidates))).all()
        }
    removed = 0
    for stem, path in candidates.items():
        if stem in known:
            continue
        try:
            path.unlink()
            removed += 1
        except OSError:
            logger.warning("Could not remove an orphaned upload file.", extra={"file": path.name})
    if removed:
        logger.info("Removed orphaned upload files.", extra={"count": removed})
    return removed


class IngestionWorker:
    """Runs process_pending in a background thread until stopped."""

    def __init__(self, session_factory, upload_dir: str):
        self.session_factory = session_factory
        self.upload_dir = upload_dir
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="ingestion-worker", daemon=True)
        self._thread.start()

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def wake(self) -> None:
        self._wake.set()

    def stop(self, timeout: float = 30.0) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout)

    def _run(self) -> None:
        next_sweep = 0.0
        while not self._stop.is_set():
            try:
                if time.monotonic() >= next_sweep:
                    remove_orphan_files(self.session_factory, self.upload_dir)
                    next_sweep = time.monotonic() + ORPHAN_SWEEP_SECONDS
                while not self._stop.is_set() and process_pending(self.session_factory, limit=1):
                    pass
            except Exception:
                # Keep the worker alive through database outages; claims are retried.
                logger.exception("Ingestion worker iteration failed.")
            self._wake.wait(POLL_SECONDS)
            self._wake.clear()
