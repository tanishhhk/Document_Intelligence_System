"""Process story jobs: write the story, then try to render its video.

Jobs are rows in video_jobs, claimed with a lease like documents are (see
app.services.ingestion), so several workers can share the table and a job
abandoned by a crashed worker is picked up again. The story is saved before
rendering starts, so it is readable while the video is still being made, and
a failed video never costs the story.
"""
import json
import logging
import shutil
import threading
import time
import uuid
from pathlib import Path

from sqlalchemy import and_, or_

from app.config import settings
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.video_job import VideoJob
from app.services.story import sample_passages, write_story
from app.services.video_render import render_story_video
from app.utils.isolated import IsolationTimeout, run_isolated

logger = logging.getLogger(__name__)

QUEUED = "queued"
RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"
ACTIVE = (QUEUED, RUNNING)

MAX_ATTEMPTS = 2
RETRY_DELAY_SECONDS = 30
POLL_SECONDS = 2.0

VIDEO_ERRORS = {
    "disabled": "Video rendering is turned off on this server. The story is ready to read.",
    "voice": "The narration voice could not be recorded, so there is no video. The story is ready to read.",
    "timeout": "The video took too long to render. The story is ready to read.",
    "render": "The video could not be rendered. The story is ready to read.",
    "expired": "Older videos are removed to save space. The story is kept.",
}


def _lease_seconds() -> int:
    return int(settings.video_render_timeout_seconds) + 300


def job_dir(job_id: str) -> Path:
    # Job ids are server-generated UUIDs, never user input.
    return Path(settings.video_dir) / job_id


def remove_job_files(job_id: str) -> None:
    shutil.rmtree(job_dir(job_id), ignore_errors=True)


def _claimable(now: int):
    return and_(
        VideoJob.status.in_(ACTIVE),
        or_(VideoJob.lease_expires_at.is_(None), VideoJob.lease_expires_at <= now),
    )


def claim_next_job(session_factory):
    """Claim the oldest queued or abandoned job. Returns (id, token) or None."""
    with session_factory() as db:
        for _ in range(5):
            now = int(time.time())
            candidate = (
                db.query(VideoJob.id).filter(_claimable(now)).order_by(VideoJob.created_at).limit(1).scalar()
            )
            if candidate is None:
                return None
            token = str(uuid.uuid4())
            claimed = (
                db.query(VideoJob)
                .filter(VideoJob.id == candidate, _claimable(now))
                .update(
                    {
                        VideoJob.status: RUNNING,
                        VideoJob.lease_token: token,
                        VideoJob.lease_expires_at: now + _lease_seconds(),
                        VideoJob.attempts: VideoJob.attempts + 1,
                    },
                    synchronize_session=False,
                )
            )
            db.commit()
            if claimed == 1:
                return candidate, token
    return None


def _update(session_factory, job_id: str, token: str, values: dict, release: bool = False) -> bool:
    """Write values if this worker still holds the job. False if it was deleted or reclaimed."""
    if release:
        values = {**values, VideoJob.lease_token: None, VideoJob.lease_expires_at: None}
    with session_factory() as db:
        updated = (
            db.query(VideoJob)
            .filter(VideoJob.id == job_id, VideoJob.lease_token == token)
            .update(values, synchronize_session=False)
        )
        db.commit()
        return updated == 1


def _load(session_factory, job_id: str):
    with session_factory() as db:
        job = db.get(VideoJob, job_id)
        if job is None:
            return None
        document = db.get(Document, job.document_id)
        chunks = (
            db.query(DocumentChunk.chunk_text, DocumentChunk.page_start, DocumentChunk.page_end)
            .filter(DocumentChunk.document_id == job.document_id)
            .order_by(DocumentChunk.chunk_index)
            .all()
        )
        return {
            "user_id": job.user_id,
            "strictness": job.strictness,
            "depth": job.depth,
            "filename": document.filename if document else "",
            "chunks": [tuple(row) for row in chunks],
        }


def _render(job_id: str, title: str, scenes) -> tuple[str, str | None]:
    """Render the video. Returns (video_status, path) where status is ready or an error key."""
    out_dir = job_dir(job_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        path = run_isolated(
            render_story_video, title, list(scenes), str(out_dir), settings.tts_voice,
            timeout=settings.video_render_timeout_seconds,
            memory_limit_bytes=settings.video_render_memory_mb * 1024 * 1024,
        )
        return "ready", path
    except IsolationTimeout:
        reason = "timeout"
    except ValueError as exc:
        reason = "voice" if str(exc) == "voice" else "render"
    except Exception:
        reason = "render"
    logger.warning("Story video was not rendered.", extra={"reason": reason})
    remove_job_files(job_id)
    return reason, None


def process_job(session_factory, job_id: str, token: str) -> None:
    """Process one claimed job. Never raises."""
    started = time.monotonic()
    try:
        job = _load(session_factory, job_id)
        if job is None:
            return
        _update(session_factory, job_id, token, {VideoJob.stage: "writing the story", VideoJob.progress: 20})
        passages = sample_passages(job["chunks"], settings.story_source_chars)
        if not passages:
            _update(
                session_factory, job_id, token,
                {
                    VideoJob.status: FAILED, VideoJob.stage: FAILED, VideoJob.progress: 100,
                    VideoJob.error_message: "This document has no text to tell a story about.",
                },
                release=True,
            )
            return

        story = write_story(job["filename"], passages, job["strictness"], job["depth"])
        story_values = {
            VideoJob.title: story.title,
            VideoJob.narration: story.narration,
            VideoJob.scenes: json.dumps([{"heading": h, "text": t} for h, t in story.scenes]),
            VideoJob.story_source: story.source,
        }
        if not settings.video_render_enabled:
            _update(
                session_factory, job_id, token,
                {
                    **story_values, VideoJob.status: COMPLETED, VideoJob.stage: COMPLETED,
                    VideoJob.progress: 100, VideoJob.video_status: "disabled",
                    VideoJob.video_error: VIDEO_ERRORS["disabled"],
                },
                release=True,
            )
            return

        if not _update(
            session_factory, job_id, token,
            {
                **story_values, VideoJob.stage: "story ready; recording the narration and rendering the video",
                VideoJob.progress: 60, VideoJob.video_status: "rendering",
            },
        ):
            return  # Deleted with its document while the story was being written.

        video_status, path = _render(job_id, story.title, story.scenes)
        finished = _update(
            session_factory, job_id, token,
            {
                VideoJob.status: COMPLETED, VideoJob.stage: COMPLETED, VideoJob.progress: 100,
                VideoJob.video_status: "ready" if path else "unavailable",
                VideoJob.video_error: None if path else VIDEO_ERRORS[video_status],
                VideoJob.video_path: path,
            },
            release=True,
        )
        if not finished:
            remove_job_files(job_id)
            return
        expire_old_videos(session_factory, job["user_id"])
        logger.info(
            "Story finished.",
            extra={
                "story_source": story.source,
                "video_status": video_status,
                "duration_ms": round((time.monotonic() - started) * 1000),
            },
        )
    except Exception:
        logger.exception("Story job failed.")
        _record_failure(session_factory, job_id, token)


def _record_failure(session_factory, job_id: str, token: str) -> None:
    try:
        with session_factory() as db:
            attempts = db.query(VideoJob.attempts).filter(VideoJob.id == job_id).scalar() or MAX_ATTEMPTS
        retry = attempts < MAX_ATTEMPTS
        values = {
            VideoJob.status: QUEUED if retry else FAILED,
            VideoJob.stage: "waiting to retry" if retry else FAILED,
            VideoJob.error_message: None if retry else "The story could not be written. Try again later.",
        }
        if retry:
            values[VideoJob.lease_expires_at] = int(time.time()) + RETRY_DELAY_SECONDS
            values[VideoJob.lease_token] = None
            _update(session_factory, job_id, token, values)
        else:
            _update(session_factory, job_id, token, values, release=True)
        remove_job_files(job_id)
    except Exception:
        logger.exception("Could not record a story job failure.")


def expire_old_videos(session_factory, user_id: str) -> None:
    """Delete a user's videos beyond settings.videos_kept_per_user, keeping the stories."""
    with session_factory() as db:
        old = (
            db.query(VideoJob)
            .filter(VideoJob.user_id == user_id, VideoJob.video_status == "ready")
            .order_by(VideoJob.created_at.desc())
            .offset(settings.videos_kept_per_user)
            .all()
        )
        for job in old:
            job.video_status = "expired"
            job.video_error = VIDEO_ERRORS["expired"]
            job.video_path = None
        db.commit()
        expired = [job.id for job in old]
    for job_id in expired:
        remove_job_files(job_id)


def process_pending(session_factory, limit: int | None = None) -> int:
    processed = 0
    while limit is None or processed < limit:
        claim = claim_next_job(session_factory)
        if claim is None:
            break
        process_job(session_factory, *claim)
        processed += 1
    return processed


class VideoWorker:
    """Runs process_pending in a background thread until stopped."""

    def __init__(self, session_factory):
        self.session_factory = session_factory
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="video-worker", daemon=True)
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
        while not self._stop.is_set():
            try:
                while not self._stop.is_set() and process_pending(self.session_factory, limit=1):
                    pass
            except Exception:
                logger.exception("Video worker iteration failed.")
            self._wake.wait(POLL_SECONDS)
            self._wake.clear()
