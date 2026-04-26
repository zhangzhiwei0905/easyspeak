"""Pydantic schemas for immersive learning sessions."""
from pydantic import BaseModel
from typing import Optional, Union
from datetime import datetime


class LearnQuizOption(BaseModel):
    key: str  # 'A', 'B', 'C', 'D'
    text: str


class LearnQuiz(BaseModel):
    """A pre-generated quiz for a learning stage."""
    question: str
    options: list[LearnQuizOption]
    answer: str  # correct option key
    hint: Optional[str] = None


class LearnPhraseItem(BaseModel):
    """A phrase item with all data needed for the 4-stage learning flow."""
    id: int
    type: str = "phrase"
    phrase: str
    meaning: str
    explanation: str
    example_en: Optional[str] = None
    example_cn: Optional[str] = None
    source: Optional[str] = None
    # Pre-generated quizzes for stage 2 and 3
    stage2_quiz: LearnQuiz  # comprehension: English → Chinese meaning
    stage3_quiz: LearnQuiz  # practice: fill-in-the-blank


class LearnWordItem(BaseModel):
    """A word item with all data needed for the 4-stage learning flow."""
    id: int
    type: str = "word"
    word: str
    phonetic: Optional[str] = None
    part_of_speech: Optional[str] = None
    meaning: str
    example: Optional[str] = None
    # Pre-generated quizzes for stage 2 and 3
    stage2_quiz: LearnQuiz  # comprehension: English → Chinese meaning
    stage3_quiz: LearnQuiz  # practice: meaning → pick word, or fill blank


class LearnSessionRequest(BaseModel):
    """Request to create a learning session."""
    content_id: int  # daily_content.id
    learn_type: str = "phrase"  # 'phrase' or 'word'


class LearnSessionResponse(BaseModel):
    """Response containing all learning data for a session."""
    session_id: str
    learn_type: str  # 'phrase' or 'word'
    theme_zh: str
    theme_en: str
    items: list[Union[LearnPhraseItem, LearnWordItem]]
    total_items: int
    batch_size: int = 5


class LearnProgressItem(BaseModel):
    """Progress update for a single item."""
    item_id: int
    item_type: str  # 'phrase' or 'word'
    mastery: int  # 0-4: 0=forgot, 1=fuzzy, 3=remembered, 4=solid


class LearnProgressRequest(BaseModel):
    """Batch progress update after learning session."""
    content_id: int
    learn_type: str  # 'phrase' or 'word'
    items: list[LearnProgressItem]


class LearnReportRequest(BaseModel):
    """Submit learning report with stats."""
    content_id: int
    learn_type: str  # 'phrase' or 'word'
    total_items: int
    first_pass_correct: int  # items correct on first try in stage 2+3
    retry_correct: int  # items correct after retry
    duration_seconds: int  # total learning time
    mastery_distribution: dict[str, int]  # {"forgot": 1, "fuzzy": 3, ...}


class LearnReportResponse(BaseModel):
    """Response after submitting learning report."""
    study_streak: int
    total_study_days: int
    message: str = "学习记录已保存"
