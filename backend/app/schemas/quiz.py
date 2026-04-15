"""Pydantic schemas for quiz."""
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class QuizOption(BaseModel):
    key: str  # 'A', 'B', 'C', 'D'
    text: str


class QuizQuestion(BaseModel):
    question_id: int
    quiz_type: str  # 'phrase_meaning', 'word_phonetic', 'fill_blank'
    question_text: str
    options: list[QuizOption] = []
    answer: str  # correct option key
    hint: Optional[str] = None
    item_type: Optional[str] = None  # 'phrase' or 'word'


class QuizGenerateRequest(BaseModel):
    type: Optional[str] = "mixed"  # 'phrase', 'word', 'fill_blank', 'mixed'
    count: int = 10
    content_id: Optional[int] = None  # filter by specific daily content


class QuizSubmitAnswer(BaseModel):
    question_id: int
    answer: str
    quiz_type: Optional[str] = None  # phrase_meaning | word_phonetic | fill_blank


class QuizSubmitRequest(BaseModel):
    answers: list[QuizSubmitAnswer]


class QuizResultItem(BaseModel):
    question_id: int
    quiz_type: str
    question_text: str
    user_answer: str
    correct_answer: str
    correct: bool
    hint: Optional[str] = None  # explanation or hint for review


class QuizResult(BaseModel):
    total: int
    correct: int
    accuracy: float
    details: list[QuizResultItem]


class QuizStats(BaseModel):
    total_answered: int = 0
    total_correct: int = 0
    accuracy: float = 0.0
    current_streak: int = 0
    max_streak: int = 0
