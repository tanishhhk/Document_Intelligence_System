from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.orm import Session
import uuid
import os
from datetime import datetime
from app.utils.pdf_processor import extract_text_from_pdf
from app.utils.text_processor import chunk_text as split_text
from app.services.embeddings import generate_embeddings
from app.models.document_chunk import DocumentChunk
import uuid
from app.database import get_db
from app.models.document import Document
from app.schemas.document import DocumentResponse
from app.config import settings

router = APIRouter(prefix="/documents", tags=["Documents"])

@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Upload a PDF document"""
    
    # Validate file type
    if not file.filename.endswith('.pdf'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are allowed"
        )
    
    # Create uploads directory if it doesn't exist
    os.makedirs(settings.upload_dir, exist_ok=True)
    
    # Generate unique filename
    file_id = str(uuid.uuid4())
    file_extension = os.path.splitext(file.filename)[1]
    unique_filename = f"{file_id}{file_extension}"
    file_path = os.path.join(settings.upload_dir, unique_filename)
    
    # Save file to disk
    with open(file_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)
    
    # Get file size
    file_size = len(content)
    
# Extract text from PDF
    try:
        extracted_text = extract_text_from_pdf(file_path)
        doc_status = "completed"
    except Exception as e:
        extracted_text = ""
        doc_status = "failed"
        print(f"Error extracting text: {str(e)}")
        # Debug: Print extracted text preview
    if extracted_text:
        print(f"\n{'='*50}")
        print(f"Extracted text from: {file.filename}")
        print(f"Text length: {len(extracted_text)} characters")
        print(f"Preview (first 500 chars):\n{extracted_text[:500]}")
        print(f"{'='*50}\n")

# Chunk the text
    chunks = split_text(extracted_text)
    print(f"Created {len(chunks)} chunks from the document")
    
    # Generate embeddings for all chunks
    print("Generating embeddings...")
    embeddings = generate_embeddings(chunks)
    print(f"Generated {len(embeddings)} embeddings")
    
    # Save chunks to database
    for idx, (chunk_text, embedding) in enumerate(zip(chunks, embeddings)):
        chunk = DocumentChunk(
            id=str(uuid.uuid4()),
            document_id=file_id,
            chunk_index=idx,
            chunk_text=chunk_text
        )
        chunk.set_embedding(embedding)
        db.add(chunk)
    
    print(f"Saved {len(chunks)} chunks to database\n")
        
    
    # Save document info to database
    new_document = Document(
        id=file_id,
        user_id="temp-user-id",
        filename=file.filename,
        file_path=file_path,
        file_size=file_size,
        status=doc_status
    )
    
    db.add(new_document)
    db.commit()
    db.refresh(new_document)

    return new_document



@router.get("/list", response_model=list[DocumentResponse])
async def list_documents(db: Session = Depends(get_db)):
    """Get all uploaded documents"""
    documents = db.query(Document).all()
    return documents

@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(document_id: str, db: Session = Depends(get_db)):
    """Get a specific document by ID"""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document

@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: str,
    db: Session = Depends(get_db)
):
    """Delete a document and all its chunks"""
    # Get document
    document = db.query(Document).filter(Document.id == document_id).first()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Delete file from disk
    if os.path.exists(document.file_path):
        os.remove(document.file_path)
    
    # Delete chunks
    db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete()
    
    # Delete document record
    db.delete(document)
    db.commit()
    
    return {"message": "Document deleted successfully"}
    
