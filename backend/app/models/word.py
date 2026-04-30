"""Word model - 20 words per daily content."""
from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class Word(Base):
    __tablename__ = "words"

    id = Column(Integer, primary_key=True, autoincrement=True)
    content_id = Column(Integer, ForeignKey("daily_content.id"), nullable=False, index=True)
    word = Column(String(100), nullable=False)
    phonetic = Column(String(100))
    part_of_speech = Column(String(50))
    meaning = Column(Text)
    example = Column(Text)
    example_cn = Column(Text)
    sort_order = Column(Integer, default=0)

    content = relationship("DailyContent", back_populates="words")

    def __repr__(self):
        return f"<Word {self.word}>"
