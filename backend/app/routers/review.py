"""Review system - spaced repetition algorithm."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, date, timedelta
from app.database import get_db
from app.models.user import User, UserProgress
from app.models.phrase import Phrase
from app.models.word import Word
from app.schemas.user import (
    ReviewItem,
    MasteryUpdate,
    ProgressSummary,
    CalendarDay,
)
from app.routers.auth import get_current_user

router = APIRouter()


def calculate_next_review(mastery_level: int, review_count: int, last_review: datetime) -> datetime:
    """
    Simplified SM-2 algorithm.
    mastery_level: 0-5 (user self-assessment)
    review_count: number of previous reviews
    """
    if review_count == 0:
        interval = 1
    elif review_count == 1:
        interval = 3
    else:
        interval = 6

    if mastery_level >= 4:
        interval = int(interval * 2.5)
    elif mastery_level == 3:
        interval = int(interval * 1.5)
    elif mastery_level <= 1:
        interval = 1

    interval = min(interval, 30)
    return last_review + timedelta(days=interval)


@router.get("/due", response_model=list[ReviewItem])
async def get_due_reviews(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get items due for review today."""
    now = datetime.now()

    # Find progress records where next_review <= now
    due_records = (
        db.query(UserProgress)
        .filter(UserProgress.openid == user.openid, UserProgress.next_review <= now)
        .order_by(UserProgress.next_review)
        .limit(50)
        .all()
    )

    items = []
    for record in due_records:
        if record.phrase_id:
            phrase = db.query(Phrase).filter(Phrase.id == record.phrase_id).first()
            if phrase:
                items.append(
                    ReviewItem(
                        item_type="phrase",
                        item_id=phrase.id,
                        phrase=phrase.phrase,
                        meaning=None,
                        explanation=phrase.explanation[:100] + "..." if phrase.explanation else None,
                        next_review=record.next_review,
                    )
                )
        elif record.word_id:
            word = db.query(Word).filter(Word.id == record.word_id).first()
            if word:
                items.append(
                    ReviewItem(
                        item_type="word",
                        item_id=word.id,
                        word=word.word,
                        phonetic=word.phonetic,
                        meaning=word.meaning,
                        next_review=record.next_review,
                    )
                )
    return items


@router.post("/complete")
async def complete_review(
    updates: list[MasteryUpdate],
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark review items as completed with mastery levels."""
    now = datetime.now()
    updated = 0

    for update in updates:
        if update.mastery < 0 or update.mastery > 5:
            continue

        if update.item_type == "phrase":
            record = (
                db.query(UserProgress)
                .filter(
                    UserProgress.openid == user.openid,
                    UserProgress.phrase_id == update.item_id,
                )
                .first()
            )
        else:
            record = (
                db.query(UserProgress)
                .filter(
                    UserProgress.openid == user.openid,
                    UserProgress.word_id == update.item_id,
                )
                .first()
            )

        if record:
            record.mastery = update.mastery
            record.review_count += 1
            record.last_review = now
            record.next_review = calculate_next_review(
                update.mastery, record.review_count, now
            )
            updated += 1

    # Update user streak
    today = date.today()
    if user.last_study_date != today:
        if user.last_study_date == today - timedelta(days=1):
            user.study_streak += 1
        else:
            user.study_streak = 1
        user.total_study_days += 1
        user.last_study_date = today

    db.commit()
    return {"updated": updated, "study_streak": user.study_streak}


@router.get("/progress/summary", response_model=ProgressSummary)
async def get_progress_summary(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get user's learning progress overview."""
    from app.models.daily import DailyContent

    # Total phrases and words
    from sqlalchemy import func

    total_phrases = db.query(func.count(Phrase.id)).scalar() or 0
    total_words = db.query(func.count(Word.id)).scalar() or 0

    # Mastered items (mastery >= 4)
    mastered_phrases = (
        db.query(func.count(UserProgress.id))
        .filter(
            UserProgress.openid == user.openid,
            UserProgress.phrase_id.isnot(None),
            UserProgress.mastery >= 4,
        )
        .scalar()
        or 0
    )
    mastered_words = (
        db.query(func.count(UserProgress.id))
        .filter(
            UserProgress.openid == user.openid,
            UserProgress.word_id.isnot(None),
            UserProgress.mastery >= 4,
        )
        .scalar()
        or 0
    )

    return ProgressSummary(
        study_streak=user.study_streak or 0,
        total_study_days=user.total_study_days or 0,
        total_phrases=total_phrases,
        total_words=total_words,
        mastered_phrases=mastered_phrases,
        mastered_words=mastered_words,
    )


@router.get("/progress/calendar")
async def get_progress_calendar(
    year: int,
    month: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get study calendar for a given month."""
    start = date(year, month, 1)
    if month == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month + 1, 1)

    # Get dates where user has progress records
    records = (
        db.query(UserProgress.last_review)
        .filter(
            UserProgress.openid == user.openid,
            UserProgress.last_review >= start,
            UserProgress.last_review < end,
        )
        .distinct()
        .all()
    )

    studied_dates = {r[0].date() for r in records}

    days = []
    current = start
    while current < end:
        days.append(
            CalendarDay(
                date=current,
                studied=current in studied_dates,
            )
        )
        current += timedelta(days=1)

    return days
