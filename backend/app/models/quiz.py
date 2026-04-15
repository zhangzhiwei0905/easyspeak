"""Quiz records model."""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base


class QuizRecord(Base):
    __tablename__ = "quiz_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    openid = Column(String(64), ForeignKey("users.openid"), nullable=False, index=True)
    quiz_type = Column(String(20), nullable=False)  # 'phrase_meaning', 'word_phonetic', 'fill_blank'
    question_id = Column(Integer, nullable=False)  # phrase.id or word.id
    correct = Column(Boolean, nullable=False)
    answered_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    user = relationship("User", back_populates="quiz_records")

    def __repr__(self):
        return f"<QuizRecord {self.quiz_type} q={self.question_id} correct={self.correct}>"
