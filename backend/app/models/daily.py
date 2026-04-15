"""Daily content model - each day's push (morning/evening)."""
from sqlalchemy import Column, Integer, String, Text, Date, UniqueConstraint
from sqlalchemy.orm import relationship
from app.database import Base


class DailyContent(Base):
    __tablename__ = "daily_content"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True)
    time_slot = Column(String(10), nullable=False)  # 'morning' / 'evening'
    theme_zh = Column(String(100), nullable=False)
    theme_en = Column(String(100), nullable=False)
    introduction = Column(Text)
    practice_tips = Column(Text)

    phrases = relationship("Phrase", back_populates="content", order_by="Phrase.sort_order")
    words = relationship("Word", back_populates="content", order_by="Word.sort_order")

    __table_args__ = (
        UniqueConstraint("date", "time_slot", name="uq_date_timeslot"),
    )

    def __repr__(self):
        return f"<DailyContent {self.date} {self.time_slot}: {self.theme_zh}>"
