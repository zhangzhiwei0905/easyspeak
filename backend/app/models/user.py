"""User model and learning progress."""
from sqlalchemy import Column, Integer, String, Text, Date, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base


class User(Base):
    __tablename__ = "users"

    openid = Column(String(64), primary_key=True)
    nickname = Column(String(100))
    avatar_url = Column(Text)
    study_streak = Column(Integer, default=0)
    total_study_days = Column(Integer, default=0)
    last_study_date = Column(Date)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    progress_records = relationship("UserProgress", back_populates="user")
    quiz_records = relationship("QuizRecord", back_populates="user")
    learn_sessions = relationship("LearnSession", back_populates="user")

    def __repr__(self):
        return f"<User {self.openid}>"


class UserProgress(Base):
    __tablename__ = "user_progress"

    id = Column(Integer, primary_key=True, autoincrement=True)
    openid = Column(String(64), ForeignKey("users.openid"), nullable=False, index=True)
    word_id = Column(Integer, ForeignKey("words.id"), nullable=True, index=True)
    phrase_id = Column(Integer, ForeignKey("phrases.id"), nullable=True, index=True)
    mastery = Column(Integer, default=0)  # 0-5
    review_count = Column(Integer, default=0)
    last_review = Column(DateTime)
    next_review = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="progress_records")

    def __repr__(self):
        item = self.word_id or self.phrase_id
        return f"<UserProgress {self.openid} item={item} mastery={self.mastery}>"
