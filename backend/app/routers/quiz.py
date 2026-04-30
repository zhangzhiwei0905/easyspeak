"""Quiz system - generate questions, submit answers, and track stats."""

import asyncio
import logging
import random
import re
from collections import defaultdict
from typing import Iterable, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.daily import DailyContent
from app.models.phrase import Phrase
from app.models.quiz import QuizRecord
from app.models.user import User
from app.models.word import Word
from app.routers.auth import get_current_user
from app.schemas.quiz import (
    QuizGenerateRequest,
    QuizOption,
    QuizQuestion,
    QuizResult,
    QuizResultItem,
    QuizStats,
    QuizSubmitRequest,
    QuizThemeItem,
)
from app.utils.phrase_meaning import (
    get_phrase_learning_explanation,
    get_phrase_short_meaning,
)

logger = logging.getLogger(__name__)

router = APIRouter()

DEFAULT_QUESTION_TYPES = [
    "phrase_meaning_choice",
    "word_phonetic_choice",
    "phrase_fill_input",
]
MAX_WRONG_REVIEW_COUNT = 20


def _normalize_answer(text: Optional[str]) -> str:
    if not text:
        return ""
    return " ".join(text.strip().lower().split())


def _unique_texts(values: Iterable[str]) -> list[str]:
    seen = set()
    unique = []
    for value in values:
        normalized = _normalize_answer(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(value)
    return unique


def _get_distractors(correct: str, all_items: Iterable[str], count: int = 3) -> list[str]:
    candidates = [
        item for item in _unique_texts(all_items)
        if _normalize_answer(item) != _normalize_answer(correct)
    ]
    random.shuffle(candidates)
    return candidates[:count]


def _make_choice_options(correct_text: str, distractors: list[str]) -> Optional[list[QuizOption]]:
    if len(distractors) < 3:
        return None

    options_raw = [correct_text] + distractors[:3]
    random.shuffle(options_raw)
    return [
        QuizOption(key=chr(65 + index), text=text, is_answer=_normalize_answer(text) == _normalize_answer(correct_text))
        for index, text in enumerate(options_raw)
    ]


def _get_phrase_examples(phrase: Phrase) -> list[str]:
    return [example for example in [phrase.example_1, phrase.example_2, phrase.example_3] if example]


async def _get_ai_distractors(phrase_text: str, meaning: str, count: int = 3) -> Optional[list[str]]:
    """Try to generate AI distractors. Returns None on failure."""
    try:
        from app.utils.ai_client import generate_distractors
        return await generate_distractors(phrase_text, meaning, count)
    except Exception as e:
        logger.warning("AI distractor generation failed for '%s': %s", phrase_text, e)
        return None


def _build_phrase_meaning_question(phrase: Phrase, phrase_pool: list[Phrase], ai_distractors: Optional[list[str]] = None) -> Optional[QuizQuestion]:
    meaning = get_phrase_short_meaning(phrase)
    if not meaning:
        return None

    # Use AI-generated distractors if available, otherwise fall back to pool
    if ai_distractors and len(ai_distractors) >= 3:
        distractors = ai_distractors[:3]
    else:
        distractor_pool = [item for item in [get_phrase_short_meaning(entry) for entry in phrase_pool] if item]
        distractors = _get_distractors(meaning, distractor_pool)

    options = _make_choice_options(meaning, distractors)
    if not options:
        return None

    return QuizQuestion(
        question_id=phrase.id,
        question_type="phrase_meaning_choice",
        interaction_type="choice",
        prompt=f'"{phrase.phrase}" 是什么意思？',
        options=options,
        accepted_answers=[meaning],
        hint=get_phrase_learning_explanation(phrase),
        item_type="phrase",
    )


def _build_word_phonetic_question(word: Word, word_pool: list[Word]) -> Optional[QuizQuestion]:
    distractors = _get_distractors(word.word, [item.word for item in word_pool if item.word])
    options = _make_choice_options(word.word, distractors)
    if not options:
        return None

    return QuizQuestion(
        question_id=word.id,
        question_type="word_phonetic_choice",
        interaction_type="choice",
        prompt=f'{word.phonetic} 对应哪个单词？',
        options=options,
        accepted_answers=[word.word],
        hint=word.meaning,
        item_type="word",
    )


def _build_phrase_fill_input_question(phrase: Phrase, phrase_pool: list[Phrase] = None) -> Optional[QuizQuestion]:
    example = next((item for item in _get_phrase_examples(phrase) if _normalize_answer(phrase.phrase) in _normalize_answer(item)), None)
    if not example:
        return None

    blanked = re.sub(re.escape(phrase.phrase), "______", example, flags=re.IGNORECASE)
    if blanked == example:
        return None

    # Build candidate options (correct phrase + 3 distractors)
    if phrase_pool:
        all_texts = list(set(p.phrase for p in phrase_pool if p.phrase and _normalize_answer(p.phrase) != _normalize_answer(phrase.phrase)))
        random.shuffle(all_texts)
        distractors = all_texts[:3]
    else:
        distractors = []

    options_raw = [phrase.phrase] + distractors
    random.shuffle(options_raw)
    options = [
        QuizOption(key=chr(65 + i), text=text, is_answer=_normalize_answer(text) == _normalize_answer(phrase.phrase))
        for i, text in enumerate(options_raw)
    ]

    if len(options) < 2:
        return None

    return QuizQuestion(
        question_id=phrase.id,
        question_type="phrase_fill_input",
        interaction_type="word_select",
        prompt=f"选择正确的短语填入空白处：\n{blanked}",
        options=options,
        accepted_answers=[phrase.phrase],
        hint=get_phrase_learning_explanation(phrase),
        item_type="phrase",
    )


def _question_from_item(
    question_type: str,
    question_id: int,
    db: Session,
    phrase_pool: list[Phrase],
    word_pool: list[Word],
) -> Optional[QuizQuestion]:
    if question_type == "phrase_meaning_choice":
        phrase = db.query(Phrase).filter(Phrase.id == question_id).first()
        return _build_phrase_meaning_question(phrase, phrase_pool) if phrase else None
    if question_type == "word_phonetic_choice":
        word = db.query(Word).filter(Word.id == question_id).first()
        return _build_word_phonetic_question(word, word_pool) if word and word.phonetic else None
    if question_type == "phrase_fill_input":
        phrase = db.query(Phrase).filter(Phrase.id == question_id).first()
        return _build_phrase_fill_input_question(phrase, phrase_pool) if phrase else None
    return None


def _get_question_meta(question_id: int, question_type: str, db: Session) -> dict:
    phrase = db.query(Phrase).filter(Phrase.id == question_id).first()
    if phrase:
        meaning = get_phrase_short_meaning(phrase) or phrase.phrase
        if question_type == "phrase_fill_input":
            question = _build_phrase_fill_input_question(phrase)
            return {
                "prompt": question.prompt if question else "补全短语",
                "correct_answer": phrase.phrase,
                "hint": get_phrase_learning_explanation(phrase),
            }
        return {
            "prompt": f'"{phrase.phrase}" 是什么意思？',
            "correct_answer": meaning,
            "hint": get_phrase_learning_explanation(phrase),
        }

    word = db.query(Word).filter(Word.id == question_id).first()
    if word:
        return {
            "prompt": f'{word.phonetic or ""} 对应哪个单词？',
            "correct_answer": word.word,
            "hint": word.meaning,
        }

    return {
        "prompt": "",
        "correct_answer": "",
        "hint": None,
    }


def _latest_wrong_pairs(user: User, db: Session) -> list[tuple[int, str]]:
    records = (
        db.query(QuizRecord)
        .filter(QuizRecord.openid == user.openid)
        .order_by(QuizRecord.answered_at.desc(), QuizRecord.id.desc())
        .all()
    )

    latest_by_pair = {}
    for record in records:
        pair = (record.question_id, record.quiz_type)
        if pair not in latest_by_pair:
            latest_by_pair[pair] = record

    wrong_pairs = []
    for pair, record in latest_by_pair.items():
        if not record.correct:
            wrong_pairs.append(pair)
    return wrong_pairs


def _accuracy_percent(correct: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((correct / total) * 100, 1)


@router.get("/themes", response_model=list[QuizThemeItem])
async def get_quiz_themes(db: Session = Depends(get_db)):
    """Return available daily-content themes for theme quizzes."""
    contents = (
        db.query(DailyContent)
        .options(joinedload(DailyContent.phrases), joinedload(DailyContent.words))
        .order_by(DailyContent.date.desc())
        .all()
    )

    items = []
    for content in contents:
        phrase_count = len([
            phrase for phrase in (content.phrases or [])
            if _build_phrase_meaning_question(phrase, content.phrases or [])
        ])
        word_count = len([
            word for word in (content.words or [])
            if word.phonetic and _build_word_phonetic_question(word, content.words or [])
        ])
        phrase_fill_count = len([phrase for phrase in content.phrases or [] if _build_phrase_fill_input_question(phrase, content.phrases or [])])
        items.append(
            QuizThemeItem(
                content_id=content.id,
                theme_zh=content.theme_zh,
                theme_en=content.theme_en,
                question_count=phrase_count + word_count + phrase_fill_count,
            )
        )

    return items


@router.post("/generate", response_model=list[QuizQuestion])
async def generate_quiz(
    request: QuizGenerateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate quiz questions for the requested mode."""
    question_types = request.question_types or DEFAULT_QUESTION_TYPES
    question_count = max(1, request.question_count)
    mode = request.mode or "random"

    phrase_query = db.query(Phrase)
    word_query = db.query(Word).filter(Word.phonetic.isnot(None))
    if request.content_ids:
        phrase_query = phrase_query.filter(Phrase.content_id.in_(request.content_ids))
        word_query = word_query.filter(Word.content_id.in_(request.content_ids))

    phrase_pool = phrase_query.all()
    word_pool = word_query.all()

    questions: list[QuizQuestion] = []

    if mode == "wrong_review":
        requested_types = set(question_types)
        wrong_pairs = _latest_wrong_pairs(user, db)
        for question_id, question_type in wrong_pairs:
            if question_type not in requested_types:
                continue
            question = _question_from_item(question_type, question_id, db, phrase_pool, word_pool)
            if question:
                questions.append(question)
            if len(questions) >= min(question_count, MAX_WRONG_REVIEW_COUNT):
                break
        return questions[: min(question_count, MAX_WRONG_REVIEW_COUNT)]

    if mode == "theme" and not request.content_ids:
        raise HTTPException(status_code=422, detail="theme mode requires content_ids")

    if "phrase_meaning_choice" in question_types:
        # Pre-generate AI distractors for phrase meaning questions (with timeout)
        phrase_meanings = []
        for phrase in phrase_pool:
            meaning = get_phrase_short_meaning(phrase)
            if meaning:
                phrase_meanings.append((phrase, meaning))

        ai_distractors_map: dict[int, list[str]] = {}
        if phrase_meanings:
            try:
                # Generate AI distractors concurrently with a timeout
                async def _gen_one(p: Phrase, m: str):
                    result = await _get_ai_distractors(p.phrase, m)
                    return (p.id, result)

                tasks = [_gen_one(p, m) for p, m in phrase_meanings]
                results = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=8.0,
                )
                for result in results:
                    if isinstance(result, Exception):
                        continue
                    pid, distractors = result
                    if distractors:
                        ai_distractors_map[pid] = distractors
            except asyncio.TimeoutError:
                logger.info("AI distractor generation timed out, using fallback")

        for phrase in phrase_pool:
            ai_d = ai_distractors_map.get(phrase.id)
            question = _build_phrase_meaning_question(phrase, phrase_pool, ai_d)
            if question:
                questions.append(question)

    if "word_phonetic_choice" in question_types:
        for word in word_pool:
            question = _build_word_phonetic_question(word, word_pool)
            if question:
                questions.append(question)

    if "phrase_fill_input" in question_types:
        for phrase in phrase_pool:
            question = _build_phrase_fill_input_question(phrase, phrase_pool)
            if question:
                questions.append(question)

    if not questions:
        raise HTTPException(status_code=404, detail="没有可用的题目")

    random.shuffle(questions)
    return questions[:question_count]


@router.post("/submit", response_model=QuizResult)
async def submit_quiz(
    request: QuizSubmitRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit one or more quiz answers and persist the records."""
    details = []
    correct_count = 0

    for answer in request.answers:
        meta = _get_question_meta(answer.question_id, answer.question_type, db)
        normalized_user_answer = _normalize_answer(answer.answer)
        normalized_correct_answer = _normalize_answer(meta["correct_answer"])
        is_correct = normalized_user_answer == normalized_correct_answer

        if is_correct:
            correct_count += 1

        db.add(
            QuizRecord(
                openid=user.openid,
                quiz_type=answer.question_type,
                question_id=answer.question_id,
                correct=is_correct,
            )
        )

        details.append(
            QuizResultItem(
                question_id=answer.question_id,
                question_type=answer.question_type,
                prompt=meta["prompt"],
                user_answer=answer.answer,
                correct_answer=meta["correct_answer"],
                correct=is_correct,
                hint=meta["hint"],
            )
        )

    db.commit()

    return QuizResult(
        total=len(request.answers),
        correct=correct_count,
        accuracy=_accuracy_percent(correct_count, len(request.answers)),
        details=details,
    )


@router.get("/stats", response_model=QuizStats)
async def get_quiz_stats(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get quiz statistics for the current user."""
    records = (
        db.query(QuizRecord)
        .filter(QuizRecord.openid == user.openid)
        .order_by(QuizRecord.answered_at.desc(), QuizRecord.id.desc())
        .all()
    )

    total = len(records)
    correct = len([record for record in records if record.correct])

    current_streak = 0
    for record in records:
        if record.correct:
            current_streak += 1
        else:
            break

    max_streak = 0
    temp_streak = 0
    for record in reversed(records):
        if record.correct:
            temp_streak += 1
            max_streak = max(max_streak, temp_streak)
        else:
            temp_streak = 0

    grouped = defaultdict(lambda: {"total": 0, "correct": 0})
    latest_by_pair = {}
    for record in records:
        grouped[record.quiz_type]["total"] += 1
        if record.correct:
            grouped[record.quiz_type]["correct"] += 1

        pair = (record.question_id, record.quiz_type)
        if pair not in latest_by_pair:
            latest_by_pair[pair] = record

    by_type = []
    for question_type, stats in grouped.items():
        by_type.append(
            {
                "question_type": question_type,
                "total_answered": stats["total"],
                "total_correct": stats["correct"],
                "accuracy": _accuracy_percent(stats["correct"], stats["total"]),
            }
        )

    wrong_count = len([record for record in latest_by_pair.values() if not record.correct])

    return QuizStats(
        total_answered=total,
        total_correct=correct,
        accuracy=_accuracy_percent(correct, total),
        current_streak=current_streak,
        max_streak=max_streak,
        wrong_count=wrong_count,
        by_type=sorted(by_type, key=lambda item: item["question_type"]),
    )
