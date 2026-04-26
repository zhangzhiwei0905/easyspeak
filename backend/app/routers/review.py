"""Review system endpoints."""

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.daily import DailyContent
from app.models.learn_session import LearnSession
from app.models.phrase import Phrase
from app.models.quiz import QuizRecord
from app.models.review_log import ReviewLog
from app.models.user import User, UserProgress
from app.models.word import Word
from app.routers.auth import get_current_user
from app.schemas.user import (
    CalendarDay,
    CalendarDayDetail,
    MasteryUpdate,
    ProgressSummary,
    ReviewCompleteResponse,
    ReviewDueResponse,
    ReviewItem,
    ReviewMemorySummary,
    ReviewOverviewResponse,
)
from app.utils.spaced_repetition import calculate_next_review_at

router = APIRouter()


def _month_range(year: int, month: int) -> tuple[datetime, datetime]:
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1)
    else:
        end_date = date(year, month + 1, 1)

    start = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    end = datetime.combine(end_date, time.min, tzinfo=timezone.utc)
    return start, end


def _build_review_item(
    record: UserProgress,
    phrase: Optional[Phrase],
    word: Optional[Word],
) -> Optional[ReviewItem]:
    if phrase:
        examples = [example for example in [phrase.example_1, phrase.example_2, phrase.example_3] if example]
        return ReviewItem(
            id=phrase.id,
            item_type="phrase",
            text=phrase.phrase,
            meaning=phrase.meaning,
            explanation=phrase.explanation,
            examples=examples,
            source=phrase.source,
            next_review_at=record.next_review,
        )

    if word:
        return ReviewItem(
            id=word.id,
            item_type="word",
            text=word.word,
            phonetic=word.phonetic,
            meaning=word.meaning,
            examples=[word.example] if word.example else [],
            part_of_speech=word.part_of_speech,
            next_review_at=record.next_review,
        )

    return None


def _get_memory_summary(user: User, db: Session, now: datetime) -> ReviewMemorySummary:
    due_soon_cutoff = now + timedelta(days=1)
    consolidating_cutoff = now + timedelta(days=3)

    forgetting_count = (
        db.query(func.count(UserProgress.id))
        .filter(
            UserProgress.openid == user.openid,
            UserProgress.next_review.isnot(None),
            UserProgress.next_review <= due_soon_cutoff,
        )
        .scalar()
        or 0
    )
    consolidating_count = (
        db.query(func.count(UserProgress.id))
        .filter(
            UserProgress.openid == user.openid,
            UserProgress.next_review.isnot(None),
            UserProgress.next_review > due_soon_cutoff,
            UserProgress.next_review <= consolidating_cutoff,
        )
        .scalar()
        or 0
    )
    mastered_count = (
        db.query(func.count(UserProgress.id))
        .filter(
            UserProgress.openid == user.openid,
            UserProgress.mastery >= 4,
            UserProgress.next_review.isnot(None),
            UserProgress.next_review > consolidating_cutoff,
        )
        .scalar()
        or 0
    )

    total_phrases = db.query(func.count(Phrase.id)).scalar() or 0
    total_words = db.query(func.count(Word.id)).scalar() or 0

    today = now.date()
    daily_contents = db.query(DailyContent).filter(DailyContent.date == today).all()
    if not daily_contents:
        new_count = 0
    else:
        phrase_ids = [p.id for dc in daily_contents for p in dc.phrases]
        word_ids = [w.id for dc in daily_contents for w in dc.words]
        total_today = len(phrase_ids) + len(word_ids)
        learned_phrase = (
            db.query(func.count(UserProgress.id))
            .filter(UserProgress.openid == user.openid, UserProgress.phrase_id.in_(phrase_ids))
            .scalar() or 0
        ) if phrase_ids else 0
        learned_word = (
            db.query(func.count(UserProgress.id))
            .filter(UserProgress.openid == user.openid, UserProgress.word_id.in_(word_ids))
            .scalar() or 0
        ) if word_ids else 0
        new_count = max(total_today - learned_phrase - learned_word, 0)

    return ReviewMemorySummary(
        forgetting_count=forgetting_count,
        consolidating_count=consolidating_count,
        mastered_count=mastered_count,
        new_count=new_count,
    )


@router.get("/overview", response_model=ReviewOverviewResponse)
async def get_review_overview(
    year: int,
    month: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get review overview data for the requested month."""
    now = datetime.now(timezone.utc)
    start, end = _month_range(year, month)
    start_date = start.date()
    end_date = end.date()

    due_count = (
        db.query(func.count(UserProgress.id))
        .filter(
            UserProgress.openid == user.openid,
            UserProgress.next_review.isnot(None),
            UserProgress.next_review <= now,
        )
        .scalar()
        or 0
    )

    # --- Build rich calendar data ---
    # 1. DailyContent for the month
    daily_contents = (
        db.query(DailyContent)
        .filter(DailyContent.date >= start_date, DailyContent.date < end_date)
        .all()
    )
    content_by_date = {}
    for dc in daily_contents:
        ds = dc.date.isoformat()
        content_by_date[ds] = dc

    # 2. Persistent ReviewLog records for the month.
    review_logs = (
        db.query(ReviewLog)
        .filter(
            ReviewLog.openid == user.openid,
            ReviewLog.reviewed_at >= start,
            ReviewLog.reviewed_at < end,
        )
        .all()
    )
    review_stats_by_date = {}
    logged_item_keys = set()

    def ensure_review_stats(ds: str):
        if ds not in review_stats_by_date:
            review_stats_by_date[ds] = {
                "reviewed_count": 0,
                "mastery_values": [],
                "review_phrase_count": 0,
                "review_word_count": 0,
                "forgot_count": 0,
                "fuzzy_count": 0,
                "remembered_count": 0,
                "solid_count": 0,
            }
        return review_stats_by_date[ds]

    def add_review_stat(ds: str, item_type: str, mastery: int):
        stats = ensure_review_stats(ds)
        stats["reviewed_count"] += 1
        stats["mastery_values"].append(mastery)
        if item_type == "phrase":
            stats["review_phrase_count"] += 1
        elif item_type == "word":
            stats["review_word_count"] += 1

        if mastery <= 0:
            stats["forgot_count"] += 1
        elif mastery == 1:
            stats["fuzzy_count"] += 1
        elif mastery < 4:
            stats["remembered_count"] += 1
        else:
            stats["solid_count"] += 1

    for log in review_logs:
        ds = log.reviewed_at.date().isoformat()
        logged_item_keys.add((log.item_type, log.item_id))
        add_review_stat(ds, log.item_type, log.mastery or 0)

    # Backfill current progress rows that predate ReviewLog rollout, without
    # double-counting items that already have persistent logs.
    legacy_review_progress = (
        db.query(UserProgress)
        .filter(
            UserProgress.openid == user.openid,
            UserProgress.last_review.isnot(None),
            UserProgress.last_review >= start,
            UserProgress.last_review < end,
        )
        .all()
    )
    for rec in legacy_review_progress:
        item_type = "phrase" if rec.phrase_id else "word"
        item_id = rec.phrase_id or rec.word_id
        if not item_id or (item_type, item_id) in logged_item_keys:
            continue
        add_review_stat(rec.last_review.date().isoformat(), item_type, rec.mastery or 0)

    # 3. UserProgress.created_at in this month (for learned flag)
    learned_records = (
        db.query(UserProgress.created_at)
        .filter(
            UserProgress.openid == user.openid,
            UserProgress.created_at.isnot(None),
            UserProgress.created_at >= start,
            UserProgress.created_at < end,
        )
        .all()
    )
    learned_dates = {rec[0].date().isoformat() for rec in learned_records}

    # 4. LearnSession records for first_pass_rate
    learn_sessions = (
        db.query(LearnSession.created_at, LearnSession.first_pass_correct, LearnSession.total_items)
        .filter(
            LearnSession.openid == user.openid,
            LearnSession.created_at >= start,
            LearnSession.created_at < end,
        )
        .all()
    )
    sessions_by_date = {}
    for ls in learn_sessions:
        ds = ls[0].date().isoformat()
        sessions_by_date.setdefault(ds, []).append((ls[1], ls[2]))

    # Build day list
    calendar_dates = []
    current = start_date
    while current < end_date:
        ds = current.isoformat()
        dc = content_by_date.get(ds)
        has_content = dc is not None

        # learned: user created a progress record on this day for items in this content
        learned = ds in learned_dates and has_content

        # reviewed count & avg mastery
        review_stats = ensure_review_stats(ds)
        reviewed = review_stats["reviewed_count"]
        mastery_list = review_stats["mastery_values"]
        avg_mastery = round(sum(mastery_list) / len(mastery_list), 1) if mastery_list else 0.0

        # first_pass_rate from learn sessions
        sessions = sessions_by_date.get(ds, [])
        first_pass_rate = None
        if sessions:
            total_fp = sum(fp for fp, _ in sessions)
            total_items = sum(ti for _, ti in sessions)
            first_pass_rate = round((total_fp / total_items) * 100, 1) if total_items > 0 else None

        calendar_dates.append(CalendarDayDetail(
            date=ds,
            has_content=has_content,
            learned=learned,
            reviewed=reviewed,
            reviewed_count=reviewed,
            avg_mastery=avg_mastery,
            review_phrase_count=review_stats["review_phrase_count"],
            review_word_count=review_stats["review_word_count"],
            forgot_count=review_stats["forgot_count"],
            fuzzy_count=review_stats["fuzzy_count"],
            remembered_count=review_stats["remembered_count"],
            solid_count=review_stats["solid_count"],
            first_pass_rate=first_pass_rate,
            theme_zh=dc.theme_zh if dc else None,
            phrase_count=len(dc.phrases) if dc else 0,
            word_count=len(dc.words) if dc else 0,
        ))
        current += timedelta(days=1)

    return ReviewOverviewResponse(
        due_count=due_count,
        calendar_dates=calendar_dates,
        memory_summary=_get_memory_summary(user, db, now),
    )


@router.get("/due", response_model=ReviewDueResponse)
async def get_due_reviews(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get review items that are currently due."""
    now = datetime.now(timezone.utc)
    due_records = (
        db.query(UserProgress)
        .filter(
            UserProgress.openid == user.openid,
            UserProgress.next_review.isnot(None),
            UserProgress.next_review <= now,
        )
        .order_by(UserProgress.next_review.asc())
        .limit(50)
        .all()
    )

    items: list[ReviewItem] = []
    for record in due_records:
        phrase = None
        word = None
        if record.phrase_id:
            phrase = db.query(Phrase).filter(Phrase.id == record.phrase_id).first()
        elif record.word_id:
            word = db.query(Word).filter(Word.id == record.word_id).first()

        item = _build_review_item(record, phrase, word)
        if item:
            items.append(item)

    return ReviewDueResponse(items=items, total=len(items))


@router.post("/complete", response_model=ReviewCompleteResponse)
async def complete_review(
    update: MasteryUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark one review item as completed and reschedule it."""
    now = datetime.now(timezone.utc)

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

    next_review_at = None
    updated = 0
    if record and 0 <= update.mastery <= 5:
        record.mastery = update.mastery
        record.review_count = (record.review_count or 0) + 1
        record.last_review = now
        next_review_at = calculate_next_review_at(update.mastery, record.review_count, now)
        record.next_review = next_review_at
        db.add(
            ReviewLog(
                openid=user.openid,
                item_type=update.item_type,
                item_id=update.item_id,
                mastery=update.mastery,
                reviewed_at=now,
            )
        )
        updated = 1

    today = date.today()
    if user.last_study_date != today:
        if user.last_study_date == today - timedelta(days=1):
            user.study_streak = (user.study_streak or 0) + 1
        else:
            user.study_streak = 1
        user.total_study_days = (user.total_study_days or 0) + 1
        user.last_study_date = today

    db.commit()
    return ReviewCompleteResponse(
        updated=updated,
        next_review_at=next_review_at,
        study_streak=user.study_streak or 0,
    )


@router.get("/progress/summary", response_model=ProgressSummary)
async def get_progress_summary(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Legacy progress summary used by the profile page."""
    total_phrases = db.query(func.count(Phrase.id)).scalar() or 0
    total_words = db.query(func.count(Word.id)).scalar() or 0

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

    total_quiz = (
        db.query(func.count(QuizRecord.id))
        .filter(QuizRecord.openid == user.openid)
        .scalar()
        or 0
    )
    correct_count = (
        db.query(func.count(QuizRecord.id))
        .filter(QuizRecord.openid == user.openid, QuizRecord.correct == True)
        .scalar()
        or 0
    )
    avg_accuracy = round((correct_count / total_quiz) * 100, 1) if total_quiz > 0 else 0.0

    return ProgressSummary(
        study_streak=user.study_streak or 0,
        total_study_days=user.total_study_days or 0,
        total_phrases=total_phrases,
        total_words=total_words,
        mastered_phrases=mastered_phrases,
        mastered_words=mastered_words,
        total_quiz=total_quiz,
        avg_accuracy=avg_accuracy,
    )


@router.get("/progress/calendar", response_model=list[CalendarDay])
async def get_progress_calendar(
    year: int,
    month: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Legacy monthly calendar endpoint."""
    start, end = _month_range(year, month)
    start_date = start.date()
    end_date = end.date()

    records = (
        db.query(UserProgress.last_review)
        .filter(
            UserProgress.openid == user.openid,
            UserProgress.last_review.isnot(None),
            UserProgress.last_review >= start,
            UserProgress.last_review < end,
        )
        .distinct()
        .all()
    )

    studied_dates = {record[0].date() for record in records}

    days = []
    current = start_date
    while current < end_date:
        days.append(
            CalendarDay(
                date=current,
                studied=current in studied_dates,
            )
        )
        current += timedelta(days=1)

    return days
