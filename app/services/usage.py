"""Daily per-user limits on uploads, questions and stories.

Free model tiers have small shared daily quotas, so each user gets a fair
share. Counters reset at midnight UTC. An increment only succeeds below the
limit, in one UPDATE, so concurrent requests cannot overshoot it.
"""
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.usage import UsageCounter

KINDS = ("upload", "question", "story")
_NOUNS = {"upload": "uploads", "question": "questions", "story": "stories"}


def limits() -> dict[str, int]:
    return {
        "upload": settings.daily_uploads_per_user,
        "question": settings.daily_questions_per_user,
        "story": settings.daily_stories_per_user,
    }


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> str:
    return _now().strftime("%Y-%m-%d")


def seconds_until_reset() -> int:
    now = _now()
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((midnight - now).total_seconds()))


def used_today(db: Session, user_id: str) -> dict[str, int]:
    rows = db.query(UsageCounter.kind, UsageCounter.count).filter(
        UsageCounter.user_id == user_id, UsageCounter.day == _today()
    )
    used = dict.fromkeys(KINDS, 0)
    used.update({kind: count for kind, count in rows})
    return used


def consume(db: Session, user_id: str, kind: str) -> None:
    """Count one use, or raise 429 when today's limit is reached. The caller commits."""
    limit, day = limits()[kind], _today()
    for _ in range(2):
        incremented = (
            db.query(UsageCounter)
            .filter(
                UsageCounter.user_id == user_id,
                UsageCounter.day == day,
                UsageCounter.kind == kind,
                UsageCounter.count < limit,
            )
            .update({UsageCounter.count: UsageCounter.count + 1}, synchronize_session=False)
        )
        if incremented:
            return
        exists = (
            db.query(UsageCounter.id)
            .filter(UsageCounter.user_id == user_id, UsageCounter.day == day, UsageCounter.kind == kind)
            .first()
        )
        if exists or limit < 1:
            break
        try:
            with db.begin_nested():
                db.add(UsageCounter(user_id=user_id, day=day, kind=kind, count=1))
            return
        except IntegrityError:
            continue  # Another request created today's row first; increment it instead.
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"You have used today's {limit} {_NOUNS[kind]}. The limit resets at midnight UTC.",
        headers={"Retry-After": str(seconds_until_reset())},
    )
