"""Quiz system - generate questions, submit answers, and track stats."""

import asyncio
import logging
import random
import re
from urllib.parse import unquote
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.daily import DailyContent
from app.models.phrase import Phrase
from app.models.quiz import QuizRecord
from app.models.user import User, UserProgress
from app.models.word import Word
from app.routers.auth import get_current_user
from app.schemas.quiz import (
    QuizGenerateRequest,
    QuizOption,
    QuizQuestion,
    QuizResult,
    QuizResultItem,
    QuizCategoryItem,
    QuizStats,
    QuizSubmitRequest,
    QuizThemeItem,
)
from app.utils.phrase_meaning import (
    get_phrase_learning_explanation,
    get_phrase_short_meaning,
)
from app.utils.word_enrichment import parse_context_meanings
from app.utils.distractors import get_challenging_distractors

logger = logging.getLogger(__name__)

router = APIRouter()
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
WEEKLY_QUIZ_GOAL = 50

DEFAULT_QUESTION_TYPES = [
    "phrase_meaning_choice",
    "word_meaning_choice",
    "word_phonetic_choice",
    "meaning_to_word_choice",
    "word_context_choice",
    "phrase_fill_input",
    "meaning_to_phrase_choice",
    "phrase_reorder",
]
MAX_WRONG_REVIEW_COUNT = 20
CATEGORY_LABELS = {
    "life": "生活场景",
    "travel": "旅行出行",
    "work": "职场商务",
    "social": "社交关系",
    "shopping": "购物消费",
    "health": "医疗健康",
    "education": "学习教育",
    "communication": "电话邮件",
    "emergency": "紧急情况",
    "entertainment": "文化娱乐",
}
CATEGORY_ORDER = {key: index for index, key in enumerate(CATEGORY_LABELS)}
WORD_CONTEXT_LABELS = {
    "hotel": "酒店场景",
    "phone": "电话沟通",
    "email": "邮件表达",
}


def _normalize_category_filters(values: Optional[list[str]]) -> list[str]:
    if not values:
        return []

    label_to_key = {label: key for key, label in CATEGORY_LABELS.items()}
    normalized = []
    seen = set()
    for raw in values:
        decoded = str(raw or "")
        for _ in range(2):
            next_decoded = unquote(decoded)
            if next_decoded == decoded:
                break
            decoded = next_decoded
        for part in decoded.split(","):
            value = part.strip()
            if not value:
                continue
            key = label_to_key.get(value, value)
            if key not in seen:
                seen.add(key)
                normalized.append(key)
    return normalized


def _record_answered_at(record: QuizRecord) -> datetime:
    answered_at = record.answered_at
    if answered_at.tzinfo is None:
        return answered_at.replace(tzinfo=timezone.utc)
    return answered_at


def _quiz_record_shanghai_date(record: QuizRecord):
    return _record_answered_at(record).astimezone(SHANGHAI_TZ).date()


def _weekly_quiz_range(now: datetime) -> tuple[datetime, datetime]:
    shanghai_now = now.astimezone(SHANGHAI_TZ)
    week_start_date = shanghai_now.date() - timedelta(days=shanghai_now.weekday())
    week_start = datetime.combine(week_start_date, time.min, tzinfo=SHANGHAI_TZ)
    week_end = week_start + timedelta(days=7)
    return week_start.astimezone(timezone.utc), week_end.astimezone(timezone.utc)


def _calculate_quiz_streak_days(records: list[QuizRecord], now: datetime) -> int:
    answered_dates = {_quiz_record_shanghai_date(record) for record in records}
    if not answered_dates:
        return 0

    today = now.astimezone(SHANGHAI_TZ).date()
    cursor = today if today in answered_dates else today - timedelta(days=1)
    streak_days = 0

    while cursor in answered_dates:
        streak_days += 1
        cursor -= timedelta(days=1)

    return streak_days


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


def _get_word_context_label(context_key: Optional[str]) -> str:
    value = str(context_key or "").strip()
    if not value:
        return "常见语境"
    return WORD_CONTEXT_LABELS.get(value.lower(), value)


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


def _build_word_meaning_question(word: Word, word_pool: list[Word], ai_distractors: Optional[list[str]] = None) -> Optional[QuizQuestion]:
    meaning = word.meaning or ""
    if not meaning:
        return None

    distractors = ai_distractors[:3] if ai_distractors and len(ai_distractors) >= 3 else _get_distractors(meaning, [item.meaning for item in word_pool if item.meaning])
    options = _make_choice_options(meaning, distractors)
    if not options:
        return None

    return QuizQuestion(
        question_id=word.id,
        question_type="word_meaning_choice",
        interaction_type="choice",
        prompt=f'{word.word} 是什么意思？',
        options=options,
        accepted_answers=[meaning],
        hint=word.example,
        item_type="word",
        explanation=word.usage_note,
    )


def _build_meaning_to_word_question(word: Word, word_pool: list[Word], ai_distractors: Optional[list[str]] = None) -> Optional[QuizQuestion]:
    meaning = word.meaning or ""
    if not meaning or not word.word:
        return None

    distractors = ai_distractors[:3] if ai_distractors and len(ai_distractors) >= 3 else _get_distractors(word.word, [item.word for item in word_pool if item.word])
    options = _make_choice_options(word.word, distractors)
    if not options:
        return None

    return QuizQuestion(
        question_id=word.id,
        question_type="meaning_to_word_choice",
        interaction_type="choice",
        prompt=f'哪个英文单词表示「{meaning}」？',
        options=options,
        accepted_answers=[word.word],
        hint=None,
        item_type="word",
        explanation=word.usage_note,
    )


def _build_word_context_question(word: Word, word_pool: list[Word], ai_distractors: Optional[list[str]] = None) -> Optional[QuizQuestion]:
    contexts = parse_context_meanings(word.context_meanings)
    context = contexts[0] if contexts else None
    correct = (context or {}).get("meaning") or word.meaning or ""
    if not correct:
        return None

    fallback_pool = [item.meaning for item in word_pool if item.meaning]
    distractors = ai_distractors[:3] if ai_distractors and len(ai_distractors) >= 3 else _get_distractors(correct, fallback_pool)
    options = _make_choice_options(correct, distractors)
    if not options:
        return None

    if context:
        prompt = f'在「{_get_word_context_label(context.get("context"))}」这个语境中，{word.word} 更接近哪个意思？'
        hint = context.get("example") or word.example
    else:
        prompt = f'结合常见用法，{word.word} 更接近哪个意思？'
        hint = word.example

    return QuizQuestion(
        question_id=word.id,
        question_type="word_context_choice",
        interaction_type="choice",
        prompt=prompt,
        options=options,
        accepted_answers=[correct],
        hint=hint,
        item_type="word",
        explanation=word.usage_note,
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
        interaction_type="choice",
        prompt=f"根据语境，选择合适的短语填入空白处。\n{blanked}",
        options=options,
        accepted_answers=[phrase.phrase],
        hint=get_phrase_learning_explanation(phrase),
        item_type="phrase",
        explanation=get_phrase_learning_explanation(phrase),
    )


def _build_phrase_listening_question(phrase: Phrase, phrase_pool: list[Phrase], ai_distractors: Optional[list[str]] = None) -> Optional[QuizQuestion]:
    meaning = get_phrase_short_meaning(phrase)
    if not meaning:
        return None

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
        question_type="phrase_listening_choice",
        interaction_type="listening_choice",
        prompt="听发音，选择这个短语的含义",
        options=options,
        accepted_answers=[meaning],
        hint=get_phrase_learning_explanation(phrase),
        item_type="phrase",
        tts_text=phrase.phrase,
        explanation=get_phrase_learning_explanation(phrase),
    )


def _build_meaning_to_phrase_question(phrase: Phrase, phrase_pool: list[Phrase], ai_distractors: Optional[list[str]] = None) -> Optional[QuizQuestion]:
    meaning = get_phrase_short_meaning(phrase)
    if not meaning:
        return None

    if ai_distractors and len(ai_distractors) >= 3:
        distractors = ai_distractors[:3]
    else:
        distractor_pool = [p.phrase for p in phrase_pool if p.phrase and _normalize_answer(p.phrase) != _normalize_answer(phrase.phrase)]
        distractors = _get_distractors(phrase.phrase, distractor_pool)
    options = _make_choice_options(phrase.phrase, distractors)
    if not options:
        return None

    return QuizQuestion(
        question_id=phrase.id,
        question_type="meaning_to_phrase_choice",
        interaction_type="choice",
        prompt=f'哪个短语表示「{meaning}」？',
        options=options,
        accepted_answers=[phrase.phrase],
        hint=get_phrase_learning_explanation(phrase),
        item_type="phrase",
        explanation=get_phrase_learning_explanation(phrase),
    )


def _build_phrase_reorder_question(phrase: Phrase) -> Optional[QuizQuestion]:
    meaning = get_phrase_short_meaning(phrase)
    if not phrase.phrase or len(phrase.phrase.strip().split()) < 2 or not meaning:
        return None

    words = phrase.phrase.strip().split()
    shuffled = words.copy()
    # Ensure the shuffle actually changes the order
    for _ in range(10):
        random.shuffle(shuffled)
        if shuffled != words:
            break
    if shuffled == words:
        return None

    options = [
        QuizOption(key=chr(65 + i), text=w, is_answer=False)
        for i, w in enumerate(shuffled)
    ]

    return QuizQuestion(
        question_id=phrase.id,
        question_type="phrase_reorder",
        interaction_type="reorder",
        prompt=f"请根据中文意思「{meaning}」，选择下面乱序的英文单词并按正确顺序排列。",
        options=options,
        accepted_answers=[phrase.phrase],
        hint=None,
        item_type="phrase",
        explanation=get_phrase_learning_explanation(phrase),
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
    if question_type == "word_meaning_choice":
        word = db.query(Word).filter(Word.id == question_id).first()
        return _build_word_meaning_question(word, word_pool) if word else None
    if question_type == "word_phonetic_choice":
        word = db.query(Word).filter(Word.id == question_id).first()
        return _build_word_phonetic_question(word, word_pool) if word and word.phonetic else None
    if question_type == "meaning_to_word_choice":
        word = db.query(Word).filter(Word.id == question_id).first()
        return _build_meaning_to_word_question(word, word_pool) if word else None
    if question_type == "word_context_choice":
        word = db.query(Word).filter(Word.id == question_id).first()
        return _build_word_context_question(word, word_pool) if word else None
    if question_type == "phrase_fill_input":
        phrase = db.query(Phrase).filter(Phrase.id == question_id).first()
        return _build_phrase_fill_input_question(phrase, phrase_pool) if phrase else None
    if question_type == "phrase_listening_choice":
        phrase = db.query(Phrase).filter(Phrase.id == question_id).first()
        return _build_phrase_listening_question(phrase, phrase_pool) if phrase else None
    if question_type == "meaning_to_phrase_choice":
        phrase = db.query(Phrase).filter(Phrase.id == question_id).first()
        return _build_meaning_to_phrase_question(phrase, phrase_pool) if phrase else None
    if question_type == "phrase_reorder":
        phrase = db.query(Phrase).filter(Phrase.id == question_id).first()
        return _build_phrase_reorder_question(phrase) if phrase else None
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
        if question_type == "phrase_listening_choice":
            return {
                "prompt": "听发音，选择这个短语的含义",
                "correct_answer": meaning,
                "hint": get_phrase_learning_explanation(phrase),
            }
        if question_type == "meaning_to_phrase_choice":
            return {
                "prompt": f'哪个短语表示「{meaning}」？',
                "correct_answer": phrase.phrase,
                "hint": get_phrase_learning_explanation(phrase),
            }
        if question_type == "phrase_reorder":
            return {
                "prompt": f'请根据中文意思「{meaning}」，选择下面乱序的英文单词并按正确顺序排列。',
                "correct_answer": phrase.phrase,
                "hint": None,
            }
        return {
            "prompt": f'"{phrase.phrase}" 是什么意思？',
            "correct_answer": meaning,
            "hint": get_phrase_learning_explanation(phrase),
        }

    word = db.query(Word).filter(Word.id == question_id).first()
    if word:
        if question_type == "word_meaning_choice":
            return {
                "prompt": f'{word.word} 是什么意思？',
                "correct_answer": word.meaning or "",
                "hint": word.example or word.usage_note,
            }
        if question_type == "meaning_to_word_choice":
            return {
                "prompt": f'哪个英文单词表示「{word.meaning or ""}」？',
                "correct_answer": word.word,
                "hint": None,
            }
        if question_type == "word_context_choice":
            contexts = parse_context_meanings(word.context_meanings)
            context = contexts[0] if contexts else None
            return {
                "prompt": f'在「{_get_word_context_label(context.get("context")) if context else "常见语境"}」这个语境中，{word.word} 更接近哪个意思？',
                "correct_answer": (context or {}).get("meaning") or word.meaning or "",
                "hint": (context or {}).get("example") or word.example or word.usage_note,
            }
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


def _question_target_language(question_type: str) -> Optional[str]:
    if question_type in {"phrase_meaning_choice", "phrase_listening_choice", "word_meaning_choice", "word_context_choice"}:
        return "zh"
    if question_type in {"meaning_to_phrase_choice", "word_phonetic_choice", "meaning_to_word_choice"}:
        return "en"
    return None


def _fallback_pool_for_question(question_type: str, phrase_pool: list[Phrase], word_pool: list[Word]) -> list[str]:
    if question_type in {"phrase_meaning_choice", "phrase_listening_choice"}:
        return [value for value in [get_phrase_short_meaning(item) for item in phrase_pool] if value]
    if question_type in {"meaning_to_phrase_choice", "phrase_fill_input"}:
        return [item.phrase for item in phrase_pool if item.phrase]
    if question_type in {"word_meaning_choice", "word_context_choice"}:
        return [item.meaning for item in word_pool if item.meaning]
    if question_type in {"word_phonetic_choice", "meaning_to_word_choice"}:
        return [item.word for item in word_pool if item.word]
    return []


def _quiz_prompt_context(question: QuizQuestion, db: Session) -> dict:
    if question.item_type == "phrase":
        phrase = db.query(Phrase).filter(Phrase.id == question.question_id).first()
        if not phrase:
            return {}
        return {
            "item_text": phrase.phrase,
            "meaning": get_phrase_short_meaning(phrase) or "",
            "example": phrase.example_1 or phrase.example_2 or phrase.example_3 or "",
        }

    word = db.query(Word).filter(Word.id == question.question_id).first()
    if not word:
        return {}
    return {
        "item_text": word.word,
        "meaning": word.meaning or "",
        "part_of_speech": word.part_of_speech or "",
        "example": word.example or "",
    }


def _rebuild_with_distractors(question: QuizQuestion, distractors: list[str], db: Session, phrase_pool: list[Phrase], word_pool: list[Word]) -> Optional[QuizQuestion]:
    if question.item_type == "phrase":
        phrase = db.query(Phrase).filter(Phrase.id == question.question_id).first()
        if not phrase:
            return None
        if question.question_type == "phrase_meaning_choice":
            return _build_phrase_meaning_question(phrase, phrase_pool, distractors)
        if question.question_type == "phrase_listening_choice":
            return _build_phrase_listening_question(phrase, phrase_pool, distractors)
        if question.question_type == "meaning_to_phrase_choice":
            return _build_meaning_to_phrase_question(phrase, phrase_pool, distractors)
        if question.question_type == "phrase_fill_input":
            return _build_phrase_fill_input_question(phrase, phrase_pool)
        return None

    word = db.query(Word).filter(Word.id == question.question_id).first()
    if not word:
        return None
    if question.question_type == "word_meaning_choice":
        return _build_word_meaning_question(word, word_pool, distractors)
    if question.question_type == "meaning_to_word_choice":
        return _build_meaning_to_word_question(word, word_pool, distractors)
    if question.question_type == "word_context_choice":
        return _build_word_context_question(word, word_pool, distractors)
    return None


async def _enhance_with_ai(questions: list[QuizQuestion], phrase_pool: list[Phrase], word_pool: list[Word], db: Session) -> list[QuizQuestion]:
    """Enhance selected choice questions with versioned DeepSeek distractor cache."""
    async def enhance_one(index: int, question: QuizQuestion):
        target_language = _question_target_language(question.question_type)
        if not target_language:
            return (index, None)
        correct = question.accepted_answers[0] if question.accepted_answers else ""
        if not correct:
            return (index, None)
        context = _quiz_prompt_context(question, db)
        distractors = await get_challenging_distractors(
            db,
            scope="quiz",
            item_id=question.question_id,
            question_type=question.question_type,
            correct=correct,
            target_language=target_language,
            fallback_pool=_fallback_pool_for_question(question.question_type, phrase_pool, word_pool),
            prompt=question.prompt,
            **context,
        )
        rebuilt = _rebuild_with_distractors(question, distractors, db, phrase_pool, word_pool)
        return (index, rebuilt)

    tasks = [enhance_one(index, question) for index, question in enumerate(questions)]
    if not tasks:
        return questions

    try:
        results = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=8.0)
    except asyncio.TimeoutError:
        logger.info("AI distractor enhancement timed out")
        return questions

    for result in results:
        if isinstance(result, Exception):
            continue
        index, rebuilt = result
        if rebuilt and 0 <= index < len(questions):
            questions[index] = rebuilt
    db.commit()
    return questions


def _weighted_sample(questions: list[QuizQuestion], count: int, user: User, db: Session) -> list[QuizQuestion]:
    """Sample questions weighted by user's weakness per type. Lower accuracy → higher weight."""
    if len(questions) <= count:
        random.shuffle(questions)
        return questions

    # Get per-type accuracy from user's quiz history
    records = (
        db.query(QuizRecord)
        .filter(QuizRecord.openid == user.openid)
        .order_by(QuizRecord.answered_at.desc())
        .limit(200)
        .all()
    )

    type_stats: dict[str, dict] = defaultdict(lambda: {"total": 0, "correct": 0})
    for record in records:
        type_stats[record.quiz_type]["total"] += 1
        if record.correct:
            type_stats[record.quiz_type]["correct"] += 1

    # Calculate weight per type: lower accuracy → higher weight (min 1.0)
    type_weights: dict[str, float] = {}
    for qtype, stats in type_stats.items():
        accuracy = stats["correct"] / stats["total"] if stats["total"] > 0 else 0.5
        type_weights[qtype] = max(1.0, 5.0 - 4.0 * accuracy)  # 0%→5.0, 50%→3.0, 100%→1.0

    # Assign weight to each question
    weighted = []
    for q in questions:
        w = type_weights.get(q.question_type, 3.0)  # Default weight for unseen types
        weighted.append((q, w))

    # Weighted reservoir sampling
    selected: list[QuizQuestion] = []
    remaining = list(weighted)
    for _ in range(count):
        if not remaining:
            break
        total_w = sum(w for _, w in remaining)
        r = random.uniform(0, total_w)
        cumulative = 0
        for i, (q, w) in enumerate(remaining):
            cumulative += w
            if cumulative >= r:
                selected.append(q)
                remaining.pop(i)
                break

    random.shuffle(selected)
    return selected


def _quiz_type_to_item_info(quiz_type: str) -> tuple[Optional[str], Optional[str]]:
    """Map quiz_type to (item_type, foreign_key_column)."""
    phrase_types = {
        "phrase_meaning_choice", "phrase_fill_input", "phrase_listening_choice",
        "meaning_to_phrase_choice", "phrase_reorder",
    }
    if quiz_type in phrase_types:
        return ("phrase", "phrase_id")
    if quiz_type in {"word_meaning_choice", "word_phonetic_choice", "meaning_to_word_choice", "word_context_choice"}:
        return ("word", "word_id")
    return (None, None)


def _update_review_for_wrong_answer(openid: str, quiz_type: str, item_id: int, db: Session) -> None:
    """Add a wrong quiz answer to the review queue via UserProgress."""
    item_type, fk_column = _quiz_type_to_item_info(quiz_type)
    if not item_type:
        return

    now = datetime.now(timezone.utc)

    query = db.query(UserProgress).filter(UserProgress.openid == openid)
    if fk_column == "phrase_id":
        query = query.filter(UserProgress.phrase_id == item_id)
    else:
        query = query.filter(UserProgress.word_id == item_id)

    record = query.first()

    if record:
        # Existing record: lower mastery and set for immediate review
        record.mastery = 0
        record.review_count += 1
        record.last_review = now
        record.next_review = now  # Due immediately
    else:
        # New record: create with mastery=0, due immediately
        kwargs = {
            "openid": openid,
            "mastery": 0,
            "review_count": 0,
            "last_review": now,
            "next_review": now,
        }
        if fk_column == "phrase_id":
            kwargs["phrase_id"] = item_id
        else:
            kwargs["word_id"] = item_id
        db.add(UserProgress(**kwargs))


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
        phrases = content.phrases or []
        words = content.words or []
        phrase_count = len([
            phrase for phrase in phrases
            if _build_phrase_meaning_question(phrase, phrases)
        ])
        word_count = sum(1 for word in words if any([
            _build_word_meaning_question(word, words),
            word.phonetic and _build_word_phonetic_question(word, words),
            _build_meaning_to_word_question(word, words),
            _build_word_context_question(word, words),
        ]))
        phrase_fill_count = len([phrase for phrase in phrases if _build_phrase_fill_input_question(phrase, phrases)])
        listening_count = len([phrase for phrase in phrases if _build_phrase_listening_question(phrase, phrases)])
        meaning_to_phrase_count = len([phrase for phrase in phrases if _build_meaning_to_phrase_question(phrase, phrases)])
        reorder_count = len([phrase for phrase in phrases if _build_phrase_reorder_question(phrase)])
        items.append(
            QuizThemeItem(
                content_id=content.id,
                theme_zh=content.theme_zh,
                theme_en=content.theme_en,
                question_count=phrase_count + word_count + phrase_fill_count + listening_count + meaning_to_phrase_count + reorder_count,
            )
        )

    return items


@router.get("/categories", response_model=list[QuizCategoryItem])
async def get_quiz_categories(db: Session = Depends(get_db)):
    """Return available content categories for category-scoped theme quizzes."""
    contents = (
        db.query(DailyContent)
        .options(joinedload(DailyContent.phrases), joinedload(DailyContent.words))
        .order_by(DailyContent.date.desc())
        .all()
    )

    grouped: dict[str, dict] = {}
    for content in contents:
        key = content.category
        if not key:
            continue

        bucket = grouped.setdefault(key, {
            "key": key,
            "label": CATEGORY_LABELS.get(key, content.category_zh or key),
            "content_count": 0,
            "question_count": 0,
        })
        bucket["content_count"] += 1

        phrases = content.phrases or []
        words = content.words or []
        bucket["question_count"] += len([
            phrase for phrase in phrases
            if _build_phrase_meaning_question(phrase, phrases)
        ])
        bucket["question_count"] += sum(1 for word in words if any([
            _build_word_meaning_question(word, words),
            word.phonetic and _build_word_phonetic_question(word, words),
            _build_meaning_to_word_question(word, words),
            _build_word_context_question(word, words),
        ]))
        bucket["question_count"] += len([phrase for phrase in phrases if _build_phrase_fill_input_question(phrase, phrases)])
        bucket["question_count"] += len([phrase for phrase in phrases if _build_phrase_listening_question(phrase, phrases)])
        bucket["question_count"] += len([phrase for phrase in phrases if _build_meaning_to_phrase_question(phrase, phrases)])
        bucket["question_count"] += len([phrase for phrase in phrases if _build_phrase_reorder_question(phrase)])

    return [
        QuizCategoryItem(**item)
        for item in sorted(grouped.values(), key=lambda entry: (CATEGORY_ORDER.get(entry["key"], 999), entry["key"]))
        if item["question_count"] > 0
    ]


def _candidate_item_type(question_type: str) -> str:
    return "phrase" if question_type.startswith("phrase_") or question_type == "meaning_to_phrase_choice" else "word"


def _build_candidates(question_types: list[str], phrase_pool: list[Phrase], word_pool: list[Word]) -> list[tuple[str, object]]:
    candidates: list[tuple[str, object]] = []
    for question_type in question_types:
        if question_type == "phrase_meaning_choice":
            candidates.extend((question_type, item) for item in phrase_pool)
        elif question_type == "word_meaning_choice":
            candidates.extend((question_type, item) for item in word_pool)
        elif question_type == "word_phonetic_choice":
            candidates.extend((question_type, item) for item in word_pool if item.phonetic)
        elif question_type == "meaning_to_word_choice":
            candidates.extend((question_type, item) for item in word_pool)
        elif question_type == "word_context_choice":
            candidates.extend((question_type, item) for item in word_pool)
        elif question_type == "phrase_fill_input":
            candidates.extend((question_type, item) for item in phrase_pool)
        elif question_type == "phrase_listening_choice":
            candidates.extend((question_type, item) for item in phrase_pool)
        elif question_type == "meaning_to_phrase_choice":
            candidates.extend((question_type, item) for item in phrase_pool)
        elif question_type == "phrase_reorder":
            candidates.extend((question_type, item) for item in phrase_pool)
    random.shuffle(candidates)
    return candidates


def _build_questions_from_candidates(
    candidates: list[tuple[str, object]],
    limit: int,
    db: Session,
    phrase_pool: list[Phrase],
    word_pool: list[Word],
) -> list[QuizQuestion]:
    questions: list[QuizQuestion] = []
    seen = set()
    for question_type, item in candidates:
        key = (question_type, item.id)
        if key in seen:
            continue
        seen.add(key)
        question = _question_from_item(question_type, item.id, db, phrase_pool, word_pool)
        if question:
            questions.append(question)
        if len(questions) >= limit:
            break
    return questions


def _interleave_by_type(questions: list[QuizQuestion], count: int) -> list[QuizQuestion]:
    grouped: dict[str, list[QuizQuestion]] = defaultdict(list)
    for question in questions:
        grouped[question.question_type].append(question)
    for bucket in grouped.values():
        random.shuffle(bucket)

    selected: list[QuizQuestion] = []
    last_type = None
    while len(selected) < count and any(grouped.values()):
        available = [key for key, bucket in grouped.items() if bucket and key != last_type]
        if not available:
            available = [key for key, bucket in grouped.items() if bucket]
        key = max(available, key=lambda item: len(grouped[item]))
        selected.append(grouped[key].pop())
        last_type = key
    return selected


def _balanced_sample(questions: list[QuizQuestion], count: int) -> list[QuizQuestion]:
    phrase_questions = [question for question in questions if question.item_type == "phrase"]
    word_questions = [question for question in questions if question.item_type == "word"]
    random.shuffle(phrase_questions)
    random.shuffle(word_questions)

    phrase_target = min(len(phrase_questions), round(count * 0.6))
    word_target = min(len(word_questions), count - phrase_target)
    if phrase_target + word_target < count:
        phrase_target = min(len(phrase_questions), phrase_target + count - phrase_target - word_target)
    if phrase_target + word_target < count:
        word_target = min(len(word_questions), word_target + count - phrase_target - word_target)

    return _interleave_by_type(phrase_questions[:phrase_target] + word_questions[:word_target], count)


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
    word_query = db.query(Word)

    # Filter by content_ids or category
    effective_content_ids = request.content_ids
    category_filters = _normalize_category_filters(request.category)
    if category_filters and not effective_content_ids:
        effective_content_ids = [
            row[0] for row in db.query(DailyContent.id)
            .filter(
                (DailyContent.category.in_(category_filters))
                | (DailyContent.category_zh.in_(category_filters))
            )
            .all()
        ]

    if effective_content_ids:
        phrase_query = phrase_query.filter(Phrase.content_id.in_(effective_content_ids))
        word_query = word_query.filter(Word.content_id.in_(effective_content_ids))

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

    if mode == "theme" and not request.content_ids and not category_filters:
        raise HTTPException(status_code=422, detail="请选择至少一个类别后再开始主题测验")

    if mode == "theme" and not effective_content_ids:
        raise HTTPException(status_code=422, detail="所选类别暂无可用题目，请更换类别后重试")

    if mode == "theme" and not phrase_pool and not word_pool:
        raise HTTPException(status_code=422, detail="所选类别暂无可用题目，请更换类别后重试")

    candidates = _build_candidates(question_types, phrase_pool, word_pool)

    if not candidates:
        raise HTTPException(status_code=404, detail="没有可用的题目")

    phrase_target = round(question_count * 0.6)
    word_target = question_count - phrase_target
    phrase_candidates = [item for item in candidates if _candidate_item_type(item[0]) == "phrase"]
    word_candidates = [item for item in candidates if _candidate_item_type(item[0]) == "word"]

    questions = _build_questions_from_candidates(
        phrase_candidates,
        max(phrase_target * 3, phrase_target),
        db,
        phrase_pool,
        word_pool,
    ) + _build_questions_from_candidates(
        word_candidates,
        max(word_target * 3, word_target),
        db,
        phrase_pool,
        word_pool,
    )

    if len(questions) < question_count:
        seen = {(question.question_type, question.question_id) for question in questions}
        for question in _build_questions_from_candidates(candidates, question_count * 4, db, phrase_pool, word_pool):
            key = (question.question_type, question.question_id)
            if key not in seen:
                seen.add(key)
                questions.append(question)
            if len(questions) >= question_count:
                break

    if not questions:
        raise HTTPException(status_code=404, detail="没有可用的题目")

    if mode == "random" and len(question_types) > 1:
        weighted = _weighted_sample(questions, min(len(questions), question_count * 3), user, db)
        selected = _balanced_sample(weighted, question_count)
    else:
        selected = _balanced_sample(questions, question_count)

    selected = await _enhance_with_ai(selected, phrase_pool, word_pool, db)

    return selected


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
        else:
            _update_review_for_wrong_answer(user.openid, answer.question_type, answer.question_id, db)

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
    now = datetime.now(timezone.utc)
    week_start, week_end = _weekly_quiz_range(now)
    weekly_answered = len([
        record for record in records
        if week_start <= _record_answered_at(record) < week_end
    ])
    weekly_percent = min(100, round((weekly_answered / WEEKLY_QUIZ_GOAL) * 100))

    return QuizStats(
        total_answered=total,
        total_correct=correct,
        accuracy=_accuracy_percent(correct, total),
        current_streak=current_streak,
        max_streak=max_streak,
        streak_days=_calculate_quiz_streak_days(records, now),
        weekly_answered=weekly_answered,
        weekly_goal=WEEKLY_QUIZ_GOAL,
        weekly_percent=weekly_percent,
        wrong_count=wrong_count,
        by_type=sorted(by_type, key=lambda item: item["question_type"]),
    )
