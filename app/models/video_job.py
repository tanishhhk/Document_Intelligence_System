from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from app.database import Base


class VideoJob(Base):
    """A narrated story of one document.

    The story text is always produced: by a model when one answers, otherwise
    from the document's own sentences. The video is added when rendering works.
    """

    __tablename__ = "video_jobs"

    id = Column(String(36), primary_key=True)
    document_id = Column(
        String, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    strictness = Column(String(20), nullable=False)
    depth = Column(String(20), nullable=False)

    # queued -> running -> completed | failed
    status = Column(String(20), nullable=False, default="queued")
    stage = Column(String(100), nullable=False, default="queued")
    progress = Column(Integer, nullable=False, default=0)
    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    lease_token = Column(String(36), nullable=True)
    lease_expires_at = Column(Integer, nullable=True)
    error_message = Column(String(500), nullable=True)

    title = Column(String(200), nullable=True)
    narration = Column(Text, nullable=True)
    scenes = Column(Text, nullable=True)  # JSON list of {"heading", "text"}
    story_source = Column(String(20), nullable=True)  # "ai" or "extractive"

    # rendering, ready, unavailable, disabled or expired
    video_status = Column(String(20), nullable=True)
    video_error = Column(String(200), nullable=True)
    video_path = Column(String, nullable=True)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<VideoJob {self.id} {self.status} {self.progress}%>"
