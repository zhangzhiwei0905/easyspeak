"""Persistent review event log."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from app.database import Base


class ReviewLog(Base):
    __tablename__ = "review_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    openid = Column(String(64), ForeignKey("users.openid"), nullable=False, index=True)
    item_type = Column(String(16), nullable=False, index=True)
    item_id = Column(Integer, nullable=False, index=True)
    mastery = Column(Integer, default=0)
    reviewed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    def __repr__(self):
        return f"<ReviewLog {self.openid} {self.item_type}:{self.item_id} mastery={self.mastery}>"
