"""Pydantic schemas for quiz."""
from pydantic import BaseModel
from typing import Optional


class QuizOption(BaseModel):
    key: str  # 'A', 'B', 'C', 'D'
    text: str
    is_answer: bool = False


class QuizQuestion(BaseModel):
    question_id: int
    question_type: str  # 'phrase_meaning_choice', 'word_phonetic_choice', 'phrase_fill_input'
    interaction_type: str  # 'choice' | 'text_input'
    prompt: str
    options: list[QuizOption] = []
    placeholder: Optional[str] = None
    accepted_answers: list[str] = []
    hint: Optional[str] = None
    item_type: Optional[str] = None  # 'phrase' or 'word'


class QuizGenerateRequest(BaseModel):
    mode: Optional[str] = "random"  # 'random' | 'theme' | 'wrong_review'
    question_count: int = 10
    content_ids: Optional[list[int]] = None
    question_types: Optional[list[str]] = None


class QuizSubmitAnswer(BaseModel):
    question_id: int
    question_type: str
    answer: str


class QuizSubmitRequest(BaseModel):
    answers: list[QuizSubmitAnswer]


class QuizResultItem(BaseModel):
    question_id: int
    question_type: str
    prompt: str
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
    wrong_count: int = 0
    by_type: list[dict] = []


class QuizThemeItem(BaseModel):
    content_id: int
    theme_zh: str
    theme_en: str
    question_count: int = 0
