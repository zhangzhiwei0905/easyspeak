"""Pydantic schemas for user auth and progress."""
from pydantic import BaseModel
from typing import Optional
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


class CalendarDay(BaseModel):
    date: date
    studied: bool
    phrase_count: int = 0
    word_count: int = 0


class MasteryUpdate(BaseModel):
    item_type: str  # 'phrase' or 'word'
    item_id: int
    mastery: int  # 0-5


class ReviewItem(BaseModel):
    item_type: str  # 'phrase' or 'word'
    item_id: int
    phrase: Optional[str] = None
    word: Optional[str] = None
    phonetic: Optional[str] = None
    meaning: Optional[str] = None
    explanation: Optional[str] = None
    next_review: Optional[datetime] = None
