import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.config import settings
from app.database import get_db
from app.models.document import Document
from app.models.user import User
from app.models.video_job import VideoJob
from app.schemas.video import VideoJobDetail, VideoJobResponse, VideoRequest
from app.services import ingestion, video_jobs

router = APIRouter()


def _owned_job(db: Session, job_id: str, user_id: str) -> VideoJob:
    # PostgreSQL rejects NUL bytes in text; no real job ID contains one.
    job = None
    if "\x00" not in job_id:
        job = db.query(VideoJob).filter(VideoJob.id == job_id, VideoJob.user_id == user_id).first()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story not found.")
    return job


@router.post("/generate/{document_id}", response_model=VideoJobResponse, status_code=status.HTTP_202_ACCEPTED)
def generate_story(
    document_id: str,
    request: Request,
    body: VideoRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Start a narrated story of one of your documents, with a video when rendering works.

    Returns at once. Poll GET /videos/{id}: the story text appears before the video is done.
    """
    body = body or VideoRequest()
    document = None
    if "\x00" not in document_id:
        document = (
            db.query(Document)
            .filter(Document.id == document_id, Document.user_id == current_user.id)
            .first()
        )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    if document.status != ingestion.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The document is not ready yet. Try again once it has been processed.",
        )

    # One story at a time per user: each one costs model quota and render time.
    active = (
        db.query(VideoJob)
        .filter(VideoJob.user_id == current_user.id, VideoJob.status.in_(video_jobs.ACTIVE))
        .first()
    )
    if active is not None:
        if (active.document_id, active.strictness, active.depth) == (document_id, body.strictness, body.depth):
            return active
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Another story is still being written for you. Try again when it finishes.",
            headers={"Retry-After": "30"},
        )

    job = VideoJob(
        id=str(uuid.uuid4()),
        document_id=document_id,
        user_id=current_user.id,
        strictness=body.strictness,
        depth=body.depth,
        status=video_jobs.QUEUED,
        stage="queued",
        progress=0,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    worker = getattr(request.app.state, "video_worker", None)
    if worker is not None:
        worker.wake()
    return job


@router.get("", response_model=list[VideoJobResponse])
def list_stories(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Your 50 most recent stories, newest first."""
    return (
        db.query(VideoJob)
        .filter(VideoJob.user_id == current_user.id)
        .order_by(VideoJob.created_at.desc())
        .limit(50)
        .all()
    )


@router.get("/{job_id}", response_model=VideoJobDetail)
def get_story(job_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """A story's progress and, once written, its title, scenes and narration."""
    return _owned_job(db, job_id, current_user.id)


@router.get("/{job_id}/download")
def download_video(job_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """The story's MP4 video."""
    job = _owned_job(db, job_id, current_user.id)
    if job.video_status != "ready" or not job.video_path:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=job.video_error or "The video is not ready yet.",
        )
    path = Path(job.video_path).resolve()
    if not path.is_relative_to(Path(settings.video_dir).resolve()) or not os.path.isfile(path):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="The video is no longer available.")
    return FileResponse(path, media_type="video/mp4", filename=f"story-{job.id}.mp4")
