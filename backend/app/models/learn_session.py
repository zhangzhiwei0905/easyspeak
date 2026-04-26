"""Learn session report model."""
import json
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base


class LearnSession(Base):
    __tablename__ = "learn_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    content_id = Column(Integer, ForeignKey("daily_content.id"), nullable=True)
    openid = Column(String(64), ForeignKey("users.openid"), nullable=False, index=True)
    learn_type = Column(String(10))
    total_items = Column(Integer, default=0)
    first_pass_correct = Column(Integer, default=0)
    retry_correct = Column(Integer, default=0)
    duration_seconds = Column(Integer, default=0)
    mastery_distribution = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="learn_sessions")

    def __repr__(self):
        return f"<LearnSession {self.openid} type={self.learn_type} items={self.total_items}>"
