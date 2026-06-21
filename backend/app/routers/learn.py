"""Immersive learning session — 4-stage learning flow with pre-generated quizzes.

Stage 1: Exposure — show card
Stage 2: Comprehension — 2 rounds of varied quiz types
Stage 3: Practice — fill-blank, reverse match, context
Stage 4: Mastery — delayed recall
"""
import random
import re
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, date, timedelta, timezone
from app.database import get_db
from app.models.user import User, UserProgress
from app.models.phrase import Phrase
from app.models.word import Word
from app.models.daily import DailyContent
from app.models.learn_session import LearnSession
from app.schemas.learn import (
    LearnSessionRequest,
    LearnSessionResponse,
    LearnPhraseItem,
    LearnWordItem,
    LearnQuiz,
    LearnQuizOption,
    LearnProgressRequest,
    LearnReportRequest,
    LearnReportResponse,
)
from app.routers.auth import get_current_user
from app.utils.phrase_meaning import (
    get_phrase_learning_explanation,
    get_phrase_short_meaning,
)
from app.utils.spaced_repetition import calculate_next_review_at
from app.utils.word_enrichment import ensure_word_enrichments, parse_context_meanings
from app.utils.distractors import get_challenging_distractors

router = APIRouter()

CHINESE_DISTRACTOR_FALLBACKS = ["不太符合", "暂不确定", "无法判断"]


def _normalize_text(text: str) -> str:
    """Normalize text for comparison: lowercase, collapse whitespace, strip punctuation."""
    return re.sub(r'[^\w\s]', '', (text or "").strip().lower())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_distractors(correct: str, pool: list[str], count: int = 3) -> list[str]:
    """Pick random distractors that differ from the correct answer."""
    # Dedupe pool first to avoid picking duplicates
    seen = {correct.strip().lower()}
    unique_pool = []
    for item in pool:
        if not item:
            continue
        key = item.strip().lower()
        if key not in seen:
            seen.add(key)
            unique_pool.append(item.strip())
    random.shuffle(unique_pool)
    return unique_pool[:count]


def _contains_cjk(text: str) -> bool:
    """Return whether text contains Chinese/Japanese/Korean characters."""
    return bool(re.search(r"[\u3400-\u9fff]", text or ""))


def _dedupe_distractors(correct: str, distractors: list[str]) -> list[str]:
    seen = {correct.strip().lower()}
    unique = []
    for item in distractors:
        normalized = (item or "").strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        unique.append(normalized)
    return unique


def _make_quiz(question: str, correct_text: str, distractors: list[str], hint: Optional[str] = None) -> LearnQuiz:
    """Build a multiple-choice quiz with shuffled options."""
    distractors = _dedupe_distractors(correct_text, distractors)

    if _contains_cjk(correct_text):
        distractors = [item for item in distractors if _contains_cjk(item)]
        fallback_pool = CHINESE_DISTRACTOR_FALLBACKS
    else:
        fallback_pool = ["(无)", "(暂无)", "(无可用)"]

    distractors = distractors[:3]
    while len(distractors) < 3:
        fallback = fallback_pool[len(distractors) % len(fallback_pool)]
        if fallback.strip().lower() != correct_text.strip().lower() and fallback not in distractors:
            distractors.append(fallback)
        else:
            break

    options_raw = [correct_text] + distractors
    random.shuffle(options_raw)
    answer_key = chr(65 + options_raw.index(correct_text))  # A/B/C/D
    options = [LearnQuizOption(key=chr(65 + i), text=t) for i, t in enumerate(options_raw)]
    return LearnQuiz(question=question, options=options, answer=answer_key, hint=hint)


def _truncate(text: str, max_len: int = 60) -> str:
    if not text:
        return ""
    return text[:max_len] + "..." if len(text) > max_len else text


# ---------------------------------------------------------------------------
# POST /learn/session — create a learning session
# ---------------------------------------------------------------------------

@router.post("/session", response_model=LearnSessionResponse)
async def create_learn_session(
    request: LearnSessionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create an immersive learning session with pre-generated quizzes."""

    # 1. Load the daily content
    content = db.query(DailyContent).filter(DailyContent.id == request.content_id).first()
    if not content:
        raise HTTPException(status_code=404, detail="推送内容不存在")

    session_id = str(uuid.uuid4())[:8]

    if request.learn_type == "phrase":
        items = await _build_phrase_items(content, db)
    else:
        items = await _build_word_items(content, db)

    if not items:
        raise HTTPException(status_code=404, detail="没有可学习的内容")

    return LearnSessionResponse(
        session_id=session_id,
        learn_type=request.learn_type,
        theme_zh=content.theme_zh,
        theme_en=content.theme_en,
        items=items,
        total_items=len(items),
        batch_size=5,
    )


# ---------------------------------------------------------------------------
# Phrase quiz builders — multiple quiz types
# ---------------------------------------------------------------------------

def _get_phrase_meaning(p: Phrase) -> str:
    """Get the short phrase meaning used in choices; return empty string when unavailable."""
    return get_phrase_short_meaning(p) or ""

async def _build_phrase_items(content: DailyContent, db: Session) -> list[LearnPhraseItem]:
    """Build phrase learning items with recognition and usage-focused quizzes."""
    phrases = content.phrases
    if not phrases:
        return []

    content_meanings = [_get_phrase_meaning(p) for p in phrases if _get_phrase_meaning(p)]
    content_phrase_texts = [p.phrase for p in phrases if p.phrase]
    all_phrases_db = db.query(Phrase).all()
    all_explanations = [_get_phrase_meaning(p) for p in all_phrases_db if _get_phrase_meaning(p)]
    all_phrase_texts = [p.phrase for p in all_phrases_db if p.phrase]
    meaning_pool = content_meanings + all_explanations
    phrase_pool = content_phrase_texts + all_phrase_texts

    items = []
    for idx, p in enumerate(phrases):
        meaning = _get_phrase_meaning(p)
        stage2 = await _phrase_stage2_quiz(p, idx, meaning, meaning_pool, phrase_pool, db)
        stage3 = await _phrase_stage3_quiz(p, idx, meaning, phrase_pool, meaning_pool, db)
        example_en = p.example_1 or p.example_2 or p.example_3 or ""
        example_cn = p.example_1_cn or p.example_2_cn or p.example_3_cn or ""

        items.append(
            LearnPhraseItem(
                id=p.id,
                phrase=p.phrase,
                meaning=meaning,
                explanation=get_phrase_learning_explanation(p),
                example_en=example_en,
                example_cn=example_cn,
                source=p.source,
                stage2_quiz=stage2,
                stage3_quiz=stage3,
            )
        )

    db.commit()
    return items


async def _learn_distractors(
    db: Session,
    *,
    item_id: int,
    question_type: str,
    correct: str,
    target_language: str,
    fallback_pool: list[str],
    prompt: str,
    item_text: str = "",
    meaning: str = "",
    part_of_speech: str = "",
    example: str = "",
) -> list[str]:
    return await get_challenging_distractors(
        db,
        scope="learn",
        item_id=item_id,
        question_type=question_type,
        correct=correct,
        target_language=target_language,
        fallback_pool=fallback_pool,
        prompt=prompt,
        item_text=item_text,
        meaning=meaning,
        part_of_speech=part_of_speech,
        example=example,
        allow_ai=False,
    )


async def _phrase_stage2_quiz(p: Phrase, idx: int, meaning: str, all_explanations, all_phrase_texts, db: Session) -> LearnQuiz:
    """Recognition stage: phrase meaning, reverse meaning, and contextual meaning."""
    quiz_type = idx % 3
    example_en = p.example_1 or p.example_2 or ""

    if not meaning:
        prompt = f'哪个短语最适合这个语境？\n{example_en}' if example_en else '请选择正确的学习短语'
        distractors = await _learn_distractors(
            db, item_id=p.id, question_type="learn_phrase_context_phrase", correct=p.phrase,
            target_language="en", fallback_pool=all_phrase_texts, prompt=prompt,
            item_text=p.phrase, example=example_en,
        )
        return _make_quiz(prompt, p.phrase, distractors)

    if quiz_type == 0:
        prompt = f'{p.phrase} 是什么意思？'
        distractors = await _learn_distractors(
            db, item_id=p.id, question_type="learn_phrase_meaning", correct=meaning,
            target_language="zh", fallback_pool=all_explanations, prompt=prompt,
            item_text=p.phrase, meaning=meaning, example=example_en,
        )
        return _make_quiz(prompt, meaning, distractors)

    if quiz_type == 1:
        prompt = f'哪个英文短语表示「{meaning}」？'
        distractors = await _learn_distractors(
            db, item_id=p.id, question_type="learn_meaning_to_phrase", correct=p.phrase,
            target_language="en", fallback_pool=all_phrase_texts, prompt=prompt,
            item_text=p.phrase, meaning=meaning, example=example_en,
        )
        return _make_quiz(prompt, p.phrase, distractors)

    prompt = f'在句子 {example_en} 中，{p.phrase} 最可能的意思是？' if example_en else f'{p.phrase} 是什么意思？'
    distractors = await _learn_distractors(
        db, item_id=p.id, question_type="learn_phrase_context_meaning", correct=meaning,
        target_language="zh", fallback_pool=all_explanations, prompt=prompt,
        item_text=p.phrase, meaning=meaning, example=example_en,
    )
    return _make_quiz(prompt, meaning, distractors)


async def _phrase_stage3_quiz(p: Phrase, idx: int, meaning: str, all_phrase_texts, all_explanations, db: Session) -> LearnQuiz:
    """Usage stage: fill phrase, choose phrase by context, and whole-expression recall."""
    quiz_type = idx % 3
    example_en = p.example_1 or p.example_2 or ""

    if quiz_type == 0 and example_en and p.phrase.lower() in example_en.lower():
        blanked = re.sub(re.escape(p.phrase), "______", example_en, flags=re.IGNORECASE)
        prompt = f'选择正确的短语填入空白处：\n{blanked}'
        distractors = await _learn_distractors(
            db, item_id=p.id, question_type="learn_phrase_fill", correct=p.phrase,
            target_language="en", fallback_pool=all_phrase_texts, prompt=prompt,
            item_text=p.phrase, meaning=meaning, example=example_en,
        )
        return _make_quiz(prompt, p.phrase, distractors, hint=meaning)

    if quiz_type == 1 and example_en:
        prompt = f'哪个短语最适合这个语境？\n{example_en}'
        distractors = await _learn_distractors(
            db, item_id=p.id, question_type="learn_phrase_context_phrase", correct=p.phrase,
            target_language="en", fallback_pool=all_phrase_texts, prompt=prompt,
            item_text=p.phrase, meaning=meaning, example=example_en,
        )
        return _make_quiz(prompt, p.phrase, distractors, hint=meaning)

    prompt = f'「{meaning}」对应哪个英文短语？' if meaning else '请选择本次学习的正确短语'
    distractors = await _learn_distractors(
        db, item_id=p.id, question_type="learn_phrase_recall", correct=p.phrase,
        target_language="en", fallback_pool=all_phrase_texts, prompt=prompt,
        item_text=p.phrase, meaning=meaning, example=example_en,
    )
    return _make_quiz(prompt, p.phrase, distractors)


# ---------------------------------------------------------------------------
# Word quiz builders — multiple quiz types
# ---------------------------------------------------------------------------

async def _build_word_items(content: DailyContent, db: Session) -> list[LearnWordItem]:
    """Build word learning items with foundation and usage-focused quizzes."""
    words = content.words
    if not words:
        return []

    all_words_db = db.query(Word).all()
    content_meanings = [w.meaning for w in words if w.meaning]
    content_word_texts = [w.word for w in words if w.word]
    all_meanings = content_meanings + [w.meaning for w in all_words_db if w.meaning]
    all_word_texts = content_word_texts + [w.word for w in all_words_db if w.word]

    items = []
    for idx, w in enumerate(words):
        contexts = parse_context_meanings(w.context_meanings)
        stage2 = await _word_stage2_quiz(w, idx, all_meanings, all_word_texts, db)
        stage3 = await _word_stage3_quiz(w, idx, all_meanings, all_word_texts, contexts, db)

        items.append(
            LearnWordItem(
                id=w.id,
                word=w.word,
                phonetic=w.phonetic,
                part_of_speech=w.part_of_speech,
                meaning=w.meaning or "",
                example=w.example,
                usage_note=w.usage_note,
                context_meanings=contexts,
                stage2_quiz=stage2,
                stage3_quiz=stage3,
            )
        )

    db.commit()
    return items


async def _word_stage2_quiz(w: Word, idx: int, all_meanings, all_word_texts, db: Session) -> LearnQuiz:
    """Foundation stage: meaning, phonetic form, and Chinese-to-English recall."""
    quiz_type = idx % 3
    meaning = w.meaning or ""

    if quiz_type == 0:
        prompt = f'{w.word} 是什么意思？'
        distractors = await _learn_distractors(
            db, item_id=w.id, question_type="learn_word_meaning", correct=meaning,
            target_language="zh", fallback_pool=all_meanings, prompt=prompt,
            item_text=w.word, meaning=meaning, part_of_speech=w.part_of_speech or "", example=w.example or "",
        )
        return _make_quiz(prompt, meaning, distractors)

    if quiz_type == 1 and w.phonetic:
        prompt = f'音标 {w.phonetic} 对应哪个单词？'
        distractors = await _learn_distractors(
            db, item_id=w.id, question_type="learn_word_phonetic", correct=w.word,
            target_language="en", fallback_pool=all_word_texts, prompt=prompt,
            item_text=w.word, meaning=meaning, part_of_speech=w.part_of_speech or "", example=w.example or "",
        )
        return _make_quiz(prompt, w.word, distractors)

    prompt = f'哪个英文单词表示「{meaning}」？'
    distractors = await _learn_distractors(
        db, item_id=w.id, question_type="learn_meaning_to_word", correct=w.word,
        target_language="en", fallback_pool=all_word_texts, prompt=prompt,
        item_text=w.word, meaning=meaning, part_of_speech=w.part_of_speech or "", example=w.example or "",
    )
    return _make_quiz(prompt, w.word, distractors)


async def _word_stage3_quiz(w: Word, idx: int, all_meanings, all_word_texts, contexts: list[dict[str, str]], db: Session) -> LearnQuiz:
    """Usage stage: sentence fill, part-of-speech/collocation, and contextual meaning."""
    quiz_type = idx % 3
    meaning = w.meaning or ""

    if quiz_type == 0 and w.example and w.word.lower() in w.example.lower():
        blanked = re.sub(re.escape(w.word), "______", w.example, count=1, flags=re.IGNORECASE)
        prompt = f'选择正确的单词填入空白处：\n{blanked}'
        distractors = await _learn_distractors(
            db, item_id=w.id, question_type="learn_word_fill", correct=w.word,
            target_language="en", fallback_pool=all_word_texts, prompt=prompt,
            item_text=w.word, meaning=meaning, part_of_speech=w.part_of_speech or "", example=w.example or "",
        )
        return _make_quiz(prompt, w.word, distractors, hint=meaning)

    if quiz_type == 1:
        pos_hint = f"（{w.part_of_speech}）" if w.part_of_speech else ""
        prompt = f'哪个单词的意思是「{meaning}」{pos_hint}？'
        distractors = await _learn_distractors(
            db, item_id=w.id, question_type="learn_word_pos", correct=w.word,
            target_language="en", fallback_pool=all_word_texts, prompt=prompt,
            item_text=w.word, meaning=meaning, part_of_speech=w.part_of_speech or "", example=w.example or "",
        )
        return _make_quiz(prompt, w.word, distractors)

    context = contexts[0] if contexts else None
    if context:
        prompt = f'在「{context.get("context", "语境")}」中，{w.word} 更接近哪个意思？'
        correct = context.get("meaning") or meaning
        distractors = await _learn_distractors(
            db, item_id=w.id, question_type="learn_word_context", correct=correct,
            target_language="zh", fallback_pool=all_meanings, prompt=prompt,
            item_text=w.word, meaning=meaning, part_of_speech=w.part_of_speech or "", example=context.get("example") or w.example or "",
        )
        return _make_quiz(prompt, correct, distractors, hint=w.usage_note)

    prompt = f'单词 {w.word} 的中文意思是？'
    distractors = await _learn_distractors(
        db, item_id=w.id, question_type="learn_word_usage_meaning", correct=meaning,
        target_language="zh", fallback_pool=all_meanings, prompt=prompt,
        item_text=w.word, meaning=meaning, part_of_speech=w.part_of_speech or "", example=w.example or "",
    )
    return _make_quiz(prompt, meaning, distractors)


# ---------------------------------------------------------------------------
# POST /learn/progress — batch update mastery
# ---------------------------------------------------------------------------

@router.post("/progress")
async def update_learn_progress(
    request: LearnProgressRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Batch update mastery levels after a learning session."""
    now = datetime.now(timezone.utc)
    created = 0
    updated = 0

    for item in request.items:
        if item.mastery < 0 or item.mastery > 5:
            continue

        # Find or create progress record
        if item.item_type == "phrase":
            record = (
                db.query(UserProgress)
                .filter(UserProgress.openid == user.openid, UserProgress.phrase_id == item.item_id)
                .first()
            )
            if not record:
                record = UserProgress(
                    openid=user.openid,
                    phrase_id=item.item_id,
                    mastery=0,
                    review_count=0,
                )
                db.add(record)
                created += 1
        else:
            record = (
                db.query(UserProgress)
                .filter(UserProgress.openid == user.openid, UserProgress.word_id == item.item_id)
                .first()
            )
            if not record:
                record = UserProgress(
                    openid=user.openid,
                    word_id=item.item_id,
                    mastery=0,
                    review_count=0,
                )
                db.add(record)
                created += 1

        record.mastery = item.mastery
        record.review_count = (record.review_count or 0) + 1
        record.last_review = now
        record.next_review = calculate_next_review_at(item.mastery, record.review_count, now)
        updated += 1

    db.commit()
    return {"created": created, "updated": updated}


# ---------------------------------------------------------------------------
# POST /learn/report — submit learning report and update streak
# ---------------------------------------------------------------------------

@router.post("/report", response_model=LearnReportResponse)
async def submit_learn_report(
    request: LearnReportRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit learning session report and update user streak."""
    today = date.today()

    if user.last_study_date != today:
        if user.last_study_date == today - timedelta(days=1):
            user.study_streak = (user.study_streak or 0) + 1
        else:
            user.study_streak = 1
        user.total_study_days = (user.total_study_days or 0) + 1
        user.last_study_date = today

    import json as _json
    session_record = LearnSession(
        content_id=request.content_id,
        openid=user.openid,
        learn_type=request.learn_type,
        total_items=request.total_items,
        first_pass_correct=request.first_pass_correct,
        retry_correct=request.retry_correct,
        duration_seconds=request.duration_seconds,
        mastery_distribution=_json.dumps(request.mastery_distribution),
    )
    db.add(session_record)

    db.commit()

    return LearnReportResponse(
        study_streak=user.study_streak or 0,
        total_study_days=user.total_study_days or 0,
        message="学习记录已保存",
    )
