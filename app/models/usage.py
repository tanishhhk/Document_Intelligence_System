from sqlalchemy import Column, ForeignKey, Integer, String, UniqueConstraint

from app.database import Base


class UsageCounter(Base):
    """How many uploads, questions or stories a user has used on one UTC day."""

    __tablename__ = "usage_counters"
    __table_args__ = (UniqueConstraint("user_id", "day", "kind", name="uq_usage_counters_user_day_kind"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    day = Column(String(10), nullable=False)  # YYYY-MM-DD in UTC
    kind = Column(String(20), nullable=False)
    count = Column(Integer, nullable=False)
