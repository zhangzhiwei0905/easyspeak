"""Pydantic schemas for user auth and progress."""
from pydantic import BaseModel
from typing import Any, Optional
from datetime import date, datetime


class WxLoginRequest(BaseModel):
    code: str


class WxLoginResponse(BaseModel):
    token: str
    openid: str
    is_new_user: bool


class ProgressSummary(BaseModel):
    study_streak: int = 0
    total_study_days: int = 0
    total_phrases: int = 0
    total_words: int = 0
    mastered_phrases: int = 0
    mastered_words: int = 0
    total_quiz: int = 0
    avg_accuracy: float = 0.0


class CalendarDay(BaseModel):
    date: date
    studied: bool
    phrase_count: int = 0
    word_count: int = 0


class CalendarDayDetail(BaseModel):
    date: str
    has_content: bool = False
    learned: bool = False
    reviewed: int = 0
    reviewed_count: int = 0
    avg_mastery: float = 0.0
    review_phrase_count: int = 0
    review_word_count: int = 0
    forgot_count: int = 0
    fuzzy_count: int = 0
    remembered_count: int = 0
    solid_count: int = 0
    first_pass_rate: Optional[float] = None
    theme_zh: Optional[str] = None
    phrase_count: int = 0
    word_count: int = 0


class ReviewMemorySummary(BaseModel):
    forgetting_count: int = 0
    consolidating_count: int = 0
    mastered_count: int = 0
    new_count: int = 0


class ReviewOverviewResponse(BaseModel):
    due_count: int = 0
    today_review_count: int = 0
    calendar_dates: list[CalendarDayDetail] = []
    memory_summary: ReviewMemorySummary = ReviewMemorySummary()


class MasteryUpdate(BaseModel):
    item_type: str  # 'phrase' or 'word'
    item_id: int
    mastery: int  # 0-5


class ReviewCompleteResponse(BaseModel):
    updated: int = 0
    next_review_at: Optional[datetime] = None
    study_streak: int = 0


class ReviewItem(BaseModel):
    id: int
    item_type: str  # 'phrase' or 'word'
    text: str
    phonetic: Optional[str] = None
    meaning: Optional[str] = None
    explanation: Optional[str] = None
    examples: list[str] = []
    source: Optional[str] = None
    part_of_speech: Optional[str] = None
    next_review_at: Optional[datetime] = None
    stage2_quiz: Optional[dict[str, Any]] = None
    stage3_quiz: Optional[dict[str, Any]] = None
    final_quiz: Optional[dict[str, Any]] = None


class ReviewDueResponse(BaseModel):
    items: list[ReviewItem] = []
    total: int = 0
