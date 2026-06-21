"""Cache for AI-generated distractors to reduce API calls."""

from datetime import datetime, timezone, timedelta

from sqlalchemy import Column, Integer, String, Text, DateTime

from app.database import Base

CACHE_TTL_DAYS = 30


class DistractorCache(Base):
    __tablename__ = "distractor_cache"

    id = Column(Integer, primary_key=True)
    cache_key = Column(String(200), unique=True, nullable=False, index=True)
    distractors_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    @staticmethod
    def make_key(question_type: str, item_id: int) -> str:
        return f"{question_type}:{item_id}"

    def is_expired(self) -> bool:
        if not self.created_at:
            return True
        created_at = self.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - created_at
        return age > timedelta(days=CACHE_TTL_DAYS)
