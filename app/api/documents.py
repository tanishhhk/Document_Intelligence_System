import logging
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import get_current_user
from app.config import settings
from app.database import get_db
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.user import User
from app.schemas.document import DocumentResponse
from app.services.embeddings import generate_embeddings
from app.utils.pdf_processor import extract_text_from_pdf
from app.utils.text_processor import chunk_text as split_text

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Documents"])
_READ_CHUNK_SIZE = 1024 * 1024


def _extract_and_embed_pdf(file_path: str):
    """Run CPU-bound PDF parsing and embedding work outside the event loop."""
    extracted_text = extract_text_from_pdf(file_path)
    if not extracted_text or not extracted_text.strip():
        raise ValueError(
            "No selectable text was found in this PDF. Scanned/image-only PDFs need OCR."
        )

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
        logger.exception("Could not remove temporary upload %s", path)


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload and index a text-based PDF owned by the authenticated user."""
    filename = Path(file.filename or "").name
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF files are supported.",
        )

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    document_id = str(uuid.uuid4())
    file_path = str(upload_dir / f"{document_id}.pdf")
    file_size = 0
    prefix = bytearray()

    try:
        # Stream in bounded chunks; never read an unbounded file into memory.
        with open(file_path, "wb") as destination:
            while True:
                block = await file.read(_READ_CHUNK_SIZE)
                if not block:
                    break
                file_size += len(block)
                if file_size > settings.max_file_size:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"PDF exceeds the {settings.max_file_size}-byte upload limit.",
                    )
                if len(prefix) < 1024:
                    prefix.extend(block[: 1024 - len(prefix)])
                destination.write(block)

        if b"%PDF-" not in prefix:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="The uploaded file does not appear to be a PDF.",
            )
        if file_size == 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The file is empty.")

        try:
            chunks, embeddings = await run_in_threadpool(_extract_and_embed_pdf, file_path)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

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

        db.commit()
        db.refresh(document)
        return document

    except HTTPException:
        db.rollback()
        _remove_file(file_path)
        raise
    except Exception as exc:
        db.rollback()
        _remove_file(file_path)
        logger.exception("Failed to index uploaded PDF")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The PDF could not be processed. Check server logs for details.",
        ) from exc
    finally:
        await file.close()


@router.get("/list", response_model=list[DocumentResponse])
def list_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List only documents owned by the authenticated user."""
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
    """Fetch a document only when it belongs to the current user."""
    document = (
        db.query(Document)
        .filter(Document.id == document_id, Document.user_id == current_user.id)
        .first()
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


@router.delete("/{document_id}", status_code=status.HTTP_200_OK)
def delete_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete an owned document and its chunks."""
    document = (
        db.query(Document)
        .filter(Document.id == document_id, Document.user_id == current_user.id)
        .first()
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    file_path = document.file_path
    db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete(
        synchronize_session=False
    )
    db.delete(document)
    db.commit()
    # Delete the file only after the database transaction succeeds.
    _remove_file(file_path)
    return {"message": "Document deleted successfully"}
