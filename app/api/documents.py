import logging
import os
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile, status
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


def _claim_idempotency_key(db: Session, user_id: str, key: str):
    now = int(time.time())
    db.query(UploadIdempotency).filter(
        UploadIdempotency.user_id == user_id,
        UploadIdempotency.expires_at <= now,
    ).delete(synchronize_session=False)
    db.commit()

    existing = (
        db.query(UploadIdempotency)
        .filter(
            UploadIdempotency.user_id == user_id,
            UploadIdempotency.idempotency_key == key,
        )
        .first()
    )
    if existing is not None:
        if existing.status == "completed" and existing.document_id:
            document = _find_owned_document(db, existing.document_id, user_id)
            if document is not None:
                return None, document
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This idempotency key is already being processed or has expired.",
        )

    claim = UploadIdempotency(
        id=str(uuid.uuid4()),
        user_id=user_id,
        idempotency_key=key,
        status="processing",
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
        if existing and existing.status == "completed" and existing.document_id:
            document = _find_owned_document(db, existing.document_id, user_id)
            if document is not None:
                return None, document
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This idempotency key is already being processed.",
        )


def _release_idempotency_claim(db: Session, claim):
    if claim is None:
        return
    try:
        db.rollback()
        db.query(UploadIdempotency).filter(
            UploadIdempotency.id == claim.id,
            UploadIdempotency.status == "processing",
        ).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not release a failed upload idempotency claim.")


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
    file_size = 0
    first_bytes = bytearray()
    claim = None

    try:
        claim, existing_document = _claim_idempotency_key(
            db, current_user.id, idempotency_key
        )
        if existing_document is not None:
            return existing_document

        upload_dir.mkdir(parents=True, exist_ok=True)
        content_length = file.headers.get("content-length")
        if content_length and content_length.isdigit():
            if int(content_length) > settings.max_file_size:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="PDF exceeds the configured upload limit.",
                )

        with open(file_path, "wb") as destination:
            while True:
                block = await file.read(_READ_CHUNK_SIZE)
                if not block:
                    break

                file_size += len(block)
                if file_size > settings.max_file_size:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail="PDF exceeds the configured upload limit.",
                    )
                if len(first_bytes) < 1024:
                    first_bytes.extend(block[: 1024 - len(first_bytes)])
                destination.write(block)

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

        try:
            chunks, embeddings = await run_in_threadpool(_extract_and_embed_pdf, file_path)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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

        claim.status = "completed"
        claim.document_id = document_id
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
