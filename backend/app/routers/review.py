"""Review system endpoints."""

from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

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
from app.utils.phrase_meaning import get_phrase_short_meaning
from app.routers.learn import _get_distractors, _make_quiz

router = APIRouter()

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def _today_review_range(now: datetime) -> tuple[datetime, datetime]:
    """Return the current Shanghai calendar day range in UTC."""
    shanghai_now = now.astimezone(SHANGHAI_TZ)
    start = datetime.combine(shanghai_now.date(), time.min, tzinfo=SHANGHAI_TZ)
    end = start + timedelta(days=1)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def _today_review_cutoff(now: datetime) -> datetime:
    """Return the end of the current Shanghai day in UTC.

    Review overview/due should be stable within a calendar day: anything that
    becomes due later today is already included, instead of appearing only when
    the exact minute arrives.
    """
    return _today_review_range(now)[1]


def _month_range(year: int, month: int) -> tuple[datetime, datetime]:
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1)
    else:
        end_date = date(year, month + 1, 1)

    start = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    end = datetime.combine(end_date, time.min, tzinfo=timezone.utc)
    return start, end


def _quiz_to_dict(quiz):
    if not quiz:
        return None
    if hasattr(quiz, "model_dump"):
        return quiz.model_dump()
    return quiz.dict()


def _split_phrase_words(text: str) -> list[str]:
    return [part for part in (text or "").replace("/", " / ").split() if part]


def _keyboard_letters(answer: str) -> list[str]:
    letters = [ch.lower() for ch in (answer or "") if ch.isalpha()]
    extras = list("etaoinshrdlucmfwypvbgkqjxz")
    needed = max(0, 12 - len(letters))
    pool = letters + extras[:needed]
    # Stable-enough shuffle without importing another helper; order is not security-sensitive.
    import random
    random.shuffle(pool)
    return pool[:max(12, len(letters))]


def _build_phrase_review_quizzes(phrase: Phrase, all_phrases: list[Phrase]):
    meaning = get_phrase_short_meaning(phrase) or phrase.meaning or ""
    phrase_pool = [p.phrase for p in all_phrases if p.phrase]
    meaning_pool = [get_phrase_short_meaning(p) or p.meaning for p in all_phrases if (get_phrase_short_meaning(p) or p.meaning)]
    cn_examples = [p.example_1_cn or p.example_2_cn or p.example_3_cn for p in all_phrases]
    cn_examples = [item for item in cn_examples if item]

    stage2 = _make_quiz(
        question=f'哪个英文短语表示「{meaning}」？',
        correct_text=phrase.phrase,
        distractors=_get_distractors(phrase.phrase, phrase_pool),
        hint="根据中文选择英文",
    )

    example_en = phrase.example_1 or phrase.example_2 or phrase.example_3 or phrase.phrase
    example_cn = phrase.example_1_cn or phrase.example_2_cn or phrase.example_3_cn or meaning
    stage3 = _make_quiz(
        question=f'请选择下面这句话的正确翻译：\n{example_en}',
        correct_text=example_cn,
        distractors=_get_distractors(example_cn, cn_examples or meaning_pool),
        hint="根据英文句子选择中文翻译",
    )

    correct_words = _split_phrase_words(phrase.phrase)
    distractor_words: list[str] = []
    for other in phrase_pool:
        if other == phrase.phrase:
            continue
        for word in _split_phrase_words(other):
            if word.lower() not in {w.lower() for w in correct_words}:
                distractor_words.append(word)
            if len(distractor_words) >= 4:
                break
        if len(distractor_words) >= 4:
            break
    tiles = correct_words + distractor_words[:4]
    import random
    random.shuffle(tiles)
    final_quiz = {
        "type": "word_select",
        "prompt": meaning or "请选择正确的单词组成短语",
        "word_tiles": tiles,
        "correct_phrase": phrase.phrase,
    }
    return _quiz_to_dict(stage2), _quiz_to_dict(stage3), final_quiz


def _build_word_review_quizzes(word: Word, all_words: list[Word]):
    word_pool = [w.word for w in all_words if w.word]
    meaning_pool = [w.meaning for w in all_words if w.meaning]
    cn_examples = [getattr(w, "example_cn", None) for w in all_words if getattr(w, "example_cn", None)]

    stage2 = _make_quiz(
        question=f'哪个英文单词表示「{word.meaning or ""}」？',
        correct_text=word.word,
        distractors=_get_distractors(word.word, word_pool),
        hint="根据中文选择英文",
    )

    example_en = word.example or f"I want to use the word {word.word}."
    example_cn = getattr(word, "example_cn", None) or f"我想使用 {word.word} 这个单词。"
    stage3 = _make_quiz(
        question=f'请选择下面这句话的正确翻译：\n{example_en}',
        correct_text=example_cn,
        distractors=_get_distractors(example_cn, cn_examples or meaning_pool),
        hint="根据英文句子选择中文翻译",
    )

    final_quiz = {
        "type": "spelling_keyboard",
        "prompt": word.meaning or "请拼写这个单词",
        "answer": word.word,
        "letters": _keyboard_letters(word.word),
    }
    return _quiz_to_dict(stage2), _quiz_to_dict(stage3), final_quiz


def _build_review_item(
    record: UserProgress,
    phrase: Optional[Phrase],
    word: Optional[Word],
    phrase_pool: Optional[list[Phrase]] = None,
    word_pool: Optional[list[Word]] = None,
) -> Optional[ReviewItem]:
    phrase_pool = phrase_pool or []
    word_pool = word_pool or []
    if phrase:
        examples = [example for example in [phrase.example_1, phrase.example_2, phrase.example_3] if example]
        stage2, stage3, final_quiz = _build_phrase_review_quizzes(phrase, phrase_pool)
        return ReviewItem(
            id=phrase.id,
            item_type="phrase",
            text=phrase.phrase,
            meaning=phrase.meaning,
            explanation=phrase.explanation,
            examples=examples,
            source=phrase.source,
            next_review_at=record.next_review,
            stage2_quiz=stage2,
            stage3_quiz=stage3,
            final_quiz=final_quiz,
        )

    if word:
        stage2, stage3, final_quiz = _build_word_review_quizzes(word, word_pool)
        return ReviewItem(
            id=word.id,
            item_type="word",
            text=word.word,
            phonetic=word.phonetic,
            meaning=word.meaning,
            examples=[word.example] if word.example else [],
            part_of_speech=word.part_of_speech,
            next_review_at=record.next_review,
            stage2_quiz=stage2,
            stage3_quiz=stage3,
            final_quiz=final_quiz,
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

    today_start, today_end = _today_review_range(now)
    review_cutoff = today_end
    due_progress_rows = (
        db.query(UserProgress.phrase_id, UserProgress.word_id)
        .filter(
            UserProgress.openid == user.openid,
            UserProgress.next_review.isnot(None),
            UserProgress.next_review <= review_cutoff,
        )
        .all()
    )
    due_item_keys = {
        ("phrase", row.phrase_id) if row.phrase_id else ("word", row.word_id)
        for row in due_progress_rows
        if row.phrase_id or row.word_id
    }
    due_count = len(due_item_keys)

    reviewed_today_rows = (
        db.query(ReviewLog.item_type, ReviewLog.item_id)
        .filter(
            ReviewLog.openid == user.openid,
            ReviewLog.reviewed_at >= today_start,
            ReviewLog.reviewed_at < today_end,
        )
        .all()
    )
    reviewed_today_keys = {(row.item_type, row.item_id) for row in reviewed_today_rows}
    today_review_count = len(due_item_keys | reviewed_today_keys)

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
    review_unique_keys_by_date: dict[str, set[tuple[str, int]]] = {}
    logged_item_keys = set()

    def ensure_review_stats(ds: str):
        if ds not in review_stats_by_date:
            review_stats_by_date[ds] = {
                "mastery_values": [],
                "review_phrase_count": 0,
                "review_word_count": 0,
                "forgot_count": 0,
                "fuzzy_count": 0,
                "remembered_count": 0,
                "solid_count": 0,
            }
        return review_stats_by_date[ds]

    def add_review_stat(ds: str, item_type: str, item_id: int, mastery: int):
        stats = ensure_review_stats(ds)
        stats["mastery_values"].append(mastery)

        # Deduplicate: only count each (type, id) once per day
        if ds not in review_unique_keys_by_date:
            review_unique_keys_by_date[ds] = set()
        key = (item_type, item_id)
        if key not in review_unique_keys_by_date[ds]:
            review_unique_keys_by_date[ds].add(key)
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
        add_review_stat(ds, log.item_type, log.item_id, log.mastery or 0)

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
        add_review_stat(rec.last_review.date().isoformat(), item_type, item_id, rec.mastery or 0)

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

        # reviewed count & avg mastery (deduplicated by unique items)
        review_stats = ensure_review_stats(ds)
        reviewed = len(review_unique_keys_by_date.get(ds, set()))
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
        today_review_count=today_review_count,
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
    review_cutoff = _today_review_cutoff(now)
    due_records = (
        db.query(UserProgress)
        .filter(
            UserProgress.openid == user.openid,
            UserProgress.next_review.isnot(None),
            UserProgress.next_review <= review_cutoff,
        )
        .order_by(UserProgress.next_review.asc())
        .limit(50)
        .all()
    )

    items: list[ReviewItem] = []
    phrase_pool = db.query(Phrase).all()
    word_pool = db.query(Word).all()
    for record in due_records:
        phrase = None
        word = None
        if record.phrase_id:
            phrase = db.query(Phrase).filter(Phrase.id == record.phrase_id).first()
        elif record.word_id:
            word = db.query(Word).filter(Word.id == record.word_id).first()

        item = _build_review_item(record, phrase, word, phrase_pool, word_pool)
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
