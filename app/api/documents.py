import hashlib
import logging
import os
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import get_current_user
from app.config import settings
from app.database import get_db
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.upload_idempotency import UploadIdempotency
from app.models.user import User
from app.schemas.document import DocumentResponse
from app.services.embeddings import generate_embeddings
from app.utils.pdf_processor import extract_text_from_pdf
from app.utils.text_processor import chunk_text as split_text

logger = logging.getLogger(__name__)
router = APIRouter()
_READ_CHUNK_SIZE = 1024 * 1024
_IDEMPOTENCY_TTL_SECONDS = 24 * 60 * 60
# Longer than ingestion of a maximum-size PDF is expected to take.
_PROCESSING_LEASE_SECONDS = 15 * 60


def _extract_and_embed_pdf(file_path: str):
    """Extract and embed a bounded amount of PDF text."""
    try:
        extracted_text = extract_text_from_pdf(
            file_path,
            max_pages=settings.max_pdf_pages,
            max_chars=settings.max_pdf_chars,
        )
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(
            "The PDF could not be read. Check that it is a valid, unencrypted PDF."
        ) from exc

    if not extracted_text or not extracted_text.strip():
        raise ValueError("No selectable text was found. Scanned PDFs need OCR.")

    chunks = split_text(extracted_text)
    if not chunks:
        raise ValueError("The PDF did not produce any text chunks.")

    embeddings = generate_embeddings(chunks)
    if len(embeddings) != len(chunks):
        raise RuntimeError("Embedding generation returned an unexpected number of vectors.")
    return chunks, embeddings


def _remove_file(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError:
        logger.exception("Could not remove a temporary upload file.")


def _find_owned_document(db: Session, document_id: str, user_id: str):
    return (
        db.query(Document)
        .filter(Document.id == document_id, Document.user_id == user_id)
        .first()
    )


def _conflict(detail: str, retry_after: int | None = None) -> HTTPException:
    headers = {"Retry-After": str(retry_after)} if retry_after else None
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail, headers=headers)


def _claim_idempotency_key(db: Session, user_id: str, key: str, payload_sha256: str):
    """Reserve an upload key for this request, or resolve it to an earlier result.

    Returns (claim, None) when this request should ingest the file, or
    (None, document) when the same file was already ingested under this key.
    The unique (user_id, idempotency_key) constraint decides concurrent
    claims; there is no check-then-insert window.
    """
    now = int(time.time())
    db.query(UploadIdempotency).filter(
        UploadIdempotency.user_id == user_id,
        UploadIdempotency.expires_at <= now,
    ).delete(synchronize_session=False)
    db.commit()

    claim = UploadIdempotency(
        id=str(uuid.uuid4()),
        user_id=user_id,
        idempotency_key=key,
        status="processing",
        payload_sha256=payload_sha256,
        lease_token=str(uuid.uuid4()),
        lease_expires_at=now + _PROCESSING_LEASE_SECONDS,
        expires_at=now + _IDEMPOTENCY_TTL_SECONDS,
    )
    try:
        db.add(claim)
        db.commit()
        return claim, None
    except IntegrityError:
        db.rollback()

    existing = (
        db.query(UploadIdempotency)
        .filter(
            UploadIdempotency.user_id == user_id,
            UploadIdempotency.idempotency_key == key,
        )
        .first()
    )
    if existing is None:
        raise _conflict("This idempotency key changed state during the request. Retry the upload.")

    # Keys recorded before fingerprints were stored have no hash to compare.
    if existing.payload_sha256 is not None and existing.payload_sha256 != payload_sha256:
        raise _conflict(
            "This idempotency key was already used for a different file. "
            "Use a new key for a new upload."
        )

    if existing.status == "completed":
        document = (
            _find_owned_document(db, existing.document_id, user_id)
            if existing.document_id
            else None
        )
        if document is not None:
            return None, document
        raise _conflict(
            "The document uploaded with this idempotency key was deleted. "
            "Use a new key to upload it again."
        )

    if existing.lease_expires_at is not None and existing.lease_expires_at > now:
        raise _conflict(
            "An upload with this idempotency key is still being processed.",
            retry_after=existing.lease_expires_at - now,
        )

    # The previous attempt stopped without finishing or releasing its claim,
    # for example because the server restarted. Take it over atomically so
    # only one retry wins.
    token = str(uuid.uuid4())
    taken = (
        db.query(UploadIdempotency)
        .filter(
            UploadIdempotency.id == existing.id,
            UploadIdempotency.status == "processing",
            or_(
                UploadIdempotency.lease_expires_at.is_(None),
                UploadIdempotency.lease_expires_at <= now,
            ),
        )
        .update(
            {
                UploadIdempotency.lease_token: token,
                UploadIdempotency.lease_expires_at: now + _PROCESSING_LEASE_SECONDS,
                UploadIdempotency.payload_sha256: payload_sha256,
                UploadIdempotency.expires_at: now + _IDEMPOTENCY_TTL_SECONDS,
            },
            synchronize_session=False,
        )
    )
    db.commit()
    if taken != 1:
        raise _conflict("An upload with this idempotency key is still being processed.")
    return db.get(UploadIdempotency, existing.id, populate_existing=True), None


def _release_idempotency_claim(db: Session, claim):
    """Delete a claim this request still owns, so the client can retry the key."""
    if claim is None:
        return
    try:
        db.rollback()
        db.query(UploadIdempotency).filter(
            UploadIdempotency.id == claim.id,
            UploadIdempotency.status == "processing",
            UploadIdempotency.lease_token == claim.lease_token,
        ).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not release a failed upload idempotency claim.")


async def _save_upload(file: UploadFile, file_path: str):
    """Stream the upload to disk, returning its size, SHA-256 and first bytes."""
    digest = hashlib.sha256()
    file_size = 0
    first_bytes = bytearray()
    with open(file_path, "wb") as destination:
        while True:
            block = await file.read(_READ_CHUNK_SIZE)
            if not block:
                break
            file_size += len(block)
            if file_size > settings.max_file_size:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail="PDF exceeds the configured upload limit.",
                )
            if len(first_bytes) < 1024:
                first_bytes.extend(block[: 1024 - len(first_bytes)])
            digest.update(block)
            destination.write(block)
    return file_size, digest.hexdigest(), bytes(first_bytes)


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    idempotency_key: str = Header(
        ...,
        alias="Idempotency-Key",
        min_length=16,
        max_length=128,
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload a PDF once per user-supplied idempotency key."""
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
    if any(char not in allowed for char in idempotency_key):
        await file.close()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key may contain only letters, numbers, dots, underscores, and hyphens.",
        )

    raw_filename = (file.filename or "").replace("\\", "/")
    filename = Path(raw_filename).name
    if not filename.lower().endswith(".pdf"):
        await file.close()
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF files are supported.",
        )

    document_id = str(uuid.uuid4())
    upload_dir = Path(settings.upload_dir)
    file_path = str(upload_dir / f"{document_id}.pdf")
    claim = None

    try:
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_size, payload_sha256, first_bytes = await _save_upload(file, file_path)
        if file_size == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The uploaded file is empty.",
            )
        if b"%PDF-" not in first_bytes:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="The uploaded file does not appear to be a PDF.",
            )

        claim, existing_document = _claim_idempotency_key(
            db, current_user.id, idempotency_key, payload_sha256
        )
        if existing_document is not None:
            _remove_file(file_path)
            return existing_document

        try:
            chunks, embeddings = await run_in_threadpool(_extract_and_embed_pdf, file_path)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc),
            ) from exc

        document = Document(
            id=document_id,
            user_id=current_user.id,
            filename=filename,
            file_path=file_path,
            file_size=file_size,
            status="completed",
        )
        db.add(document)
        db.flush()

        for index, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
            chunk = DocumentChunk(
                id=str(uuid.uuid4()),
                document_id=document_id,
                chunk_index=index,
                chunk_text=chunk_text,
            )
            chunk.set_embedding(embedding)
            db.add(chunk)

        finished = (
            db.query(UploadIdempotency)
            .filter(
                UploadIdempotency.id == claim.id,
                UploadIdempotency.lease_token == claim.lease_token,
            )
            .update(
                {
                    UploadIdempotency.status: "completed",
                    UploadIdempotency.document_id: document_id,
                    UploadIdempotency.lease_expires_at: None,
                },
                synchronize_session=False,
            )
        )
        if finished != 1:
            claim = None  # A retry with the same key owns it now; leave its claim alone.
            raise _conflict(
                "This upload took too long and was taken over by a retry with the same key."
            )
        db.commit()
        db.refresh(document)
        return document

    except HTTPException:
        db.rollback()
        _release_idempotency_claim(db, claim)
        _remove_file(file_path)
        raise
    except Exception as exc:
        db.rollback()
        _release_idempotency_claim(db, claim)
        _remove_file(file_path)
        logger.exception("PDF ingestion failed.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The PDF could not be processed. Check the server logs.",
        ) from exc
    finally:
        await file.close()


@router.get("/list", response_model=list[DocumentResponse])
def list_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return (
        db.query(Document)
        .filter(Document.user_id == current_user.id)
        .order_by(Document.upload_date.desc())
        .all()
    )


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = _find_owned_document(db, document_id, current_user.id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return document


@router.delete("/{document_id}")
def delete_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = _find_owned_document(db, document_id, current_user.id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    file_path = document.file_path
    db.query(DocumentChunk).filter(
        DocumentChunk.document_id == document_id
    ).delete(synchronize_session=False)
    db.delete(document)
    db.commit()
    _remove_file(file_path)
    return {"message": "Document deleted successfully."}
