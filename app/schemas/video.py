import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class VideoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # strict: only the document's facts. exam: may explain in its own words.
    strictness: Literal["strict", "exam"] = "strict"
    # overview: about 250 words. detailed: about 600 words.
    depth: Literal["overview", "detailed"] = "overview"


class StoryScene(BaseModel):
    heading: str
    text: str


class VideoJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    strictness: str
    depth: str
    status: str
    stage: str
    progress: int
    error: str | None = Field(default=None, validation_alias="error_message")
    story_source: str | None = None
    video_status: str | None = None
    created_at: datetime


class VideoJobDetail(VideoJobResponse):
    title: str | None = None
    narration: str | None = None
    scenes: list[StoryScene] = []
    video_error: str | None = None

    @field_validator("scenes", mode="before")
    @classmethod
    def _decode_scenes(cls, value):
        if value is None:
            return []
        return json.loads(value) if isinstance(value, str) else value
