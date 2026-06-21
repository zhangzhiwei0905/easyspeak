"""Pydantic schemas for quiz."""
from pydantic import BaseModel
from typing import Optional


class QuizOption(BaseModel):
    key: str  # 'A', 'B', 'C', 'D'
    text: str
    is_answer: bool = False


class QuizQuestion(BaseModel):
    question_id: int
    question_type: str  # phrase/word choice, listening, fill, reorder question type
    interaction_type: str  # 'choice' | 'word_select' | 'listening_choice' | 'reorder'
    prompt: str
    options: list[QuizOption] = []
    placeholder: Optional[str] = None
    accepted_answers: list[str] = []
    hint: Optional[str] = None
    item_type: Optional[str] = None  # 'phrase' or 'word'
    tts_text: Optional[str] = None  # text for frontend TTS playback
    explanation: Optional[str] = None  # detailed explanation for review


class QuizGenerateRequest(BaseModel):
    mode: Optional[str] = "random"  # 'random' | 'theme' | 'wrong_review'
    question_count: int = 10
    content_ids: Optional[list[int]] = None
    question_types: Optional[list[str]] = None
    category: Optional[list[str]] = None  # filter by content category keys


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
    streak_days: int = 0
    weekly_answered: int = 0
    weekly_goal: int = 50
    weekly_percent: int = 0
    wrong_count: int = 0
    by_type: list[dict] = []


class QuizThemeItem(BaseModel):
    content_id: int
    theme_zh: str
    theme_en: str
    question_count: int = 0


class QuizCategoryItem(BaseModel):
    key: str
    label: str
    content_count: int = 0
    question_count: int = 0
