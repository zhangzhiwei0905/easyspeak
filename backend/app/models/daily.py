"""Daily content model - each day's push."""
from sqlalchemy import Column, Integer, String, Text, Date, UniqueConstraint, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class DailyContent(Base):
    __tablename__ = "daily_content"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True)
    theme_zh = Column(String(100), nullable=False)
    theme_en = Column(String(100), nullable=False)
    introduction = Column(Text)
    practice_tips = Column(Text)
    category = Column(String(20), nullable=False)
    category_zh = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False, default="scheduled")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    phrases = relationship("Phrase", back_populates="content", order_by="Phrase.sort_order")
    words = relationship("Word", back_populates="content", order_by="Word.sort_order")

    __table_args__ = (
        UniqueConstraint("date", name="uq_date"),
    )

    def __repr__(self):
        return f"<DailyContent {self.date}: {self.theme_zh}>"
