"""Phrase model - 5 phrases per daily content."""
from sqlalchemy import Column, Integer, String, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class Phrase(Base):
    __tablename__ = "phrases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    content_id = Column(Integer, ForeignKey("daily_content.id"), nullable=False, index=True)
    phrase = Column(String(200), nullable=False)
    explanation = Column(Text, nullable=False)
    example_1 = Column(Text)
    example_1_cn = Column(Text)
    example_2 = Column(Text)
    example_2_cn = Column(Text)
    example_3 = Column(Text)
    example_3_cn = Column(Text)
    source = Column(String(200))
    sort_order = Column(Integer, default=0)

    content = relationship("DailyContent", back_populates="phrases")

    def __repr__(self):
        return f"<Phrase {self.phrase}>"
