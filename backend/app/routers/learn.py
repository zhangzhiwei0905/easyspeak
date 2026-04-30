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
        items = _build_phrase_items(content, db)
    else:
        items = _build_word_items(content, db)

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

def _build_phrase_items(content: DailyContent, db: Session) -> list[LearnPhraseItem]:
    """Build phrase learning items with RICH, varied quizzes."""
    phrases = content.phrases
    if not phrases:
        return []

    # Build distractor pools from ALL phrases in DB
    all_phrases_db = db.query(Phrase).all()
    all_explanations = [_get_phrase_meaning(p) for p in all_phrases_db]
    # Filter out phrases whose meaning is just the phrase text itself (last-resort fallback)
    all_explanations = [e for e in all_explanations if e]
    all_phrase_texts = [p.phrase for p in all_phrases_db]

    # Collect example sentences for context-based quizzes
    all_examples = []
    for p in all_phrases_db:
        if p.example_1_cn:
            all_examples.append(p.example_1_cn)
        if p.example_2_cn:
            all_examples.append(p.example_2_cn)

    items = []
    for idx, p in enumerate(phrases):
        meaning = _get_phrase_meaning(p)

        # -- Pick varied quiz types for Stage 2 & 3 --
        stage2 = _phrase_stage2_quiz(p, idx, meaning, all_explanations, all_phrase_texts, all_examples)
        stage3 = _phrase_stage3_quiz(p, idx, meaning, all_phrase_texts, all_explanations)

        # Pick best example
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

    return items


def _phrase_stage2_quiz(p: Phrase, idx: int, meaning: str, all_explanations, all_phrase_texts, all_examples) -> LearnQuiz:
    """Generate a VARIED Stage 2 quiz for a phrase. Rotate through 3 types."""
    quiz_type = idx % 3
    example_en = p.example_1 or p.example_2 or ""

    if not meaning:
        distractors = _get_distractors(p.phrase, all_phrase_texts)
        if example_en:
            return _make_quiz(
                question=f'哪个短语最适合这个语境？\n{example_en}',
                correct_text=p.phrase,
                distractors=distractors,
            )
        return _make_quiz(
            question='请选择正确的学习短语',
            correct_text=p.phrase,
            distractors=distractors,
        )

    if quiz_type == 0:
        # Type A: 看英选中 — see phrase, pick Chinese meaning
        distractors = _get_distractors(meaning, all_explanations)
        return _make_quiz(
            question=f'{p.phrase} 是什么意思？',
            correct_text=meaning,
            distractors=distractors,
        )

    elif quiz_type == 1:
        # Type B: 看中选英 — see Chinese meaning, pick English phrase
        distractors = _get_distractors(p.phrase, all_phrase_texts)
        return _make_quiz(
            question=f'哪个英文短语表示「{meaning}」？',
            correct_text=p.phrase,
            distractors=distractors,
        )

    else:
        # Type C: 例句理解 — show example sentence, ask what phrase means
        if example_en and _normalize_text(example_en) != _normalize_text(p.phrase):
            distractors = _get_distractors(meaning, all_explanations)
            return _make_quiz(
                question=f'在句子 {example_en} 中，{p.phrase} 最可能的意思是？',
                correct_text=meaning,
                distractors=distractors,
            )
        else:
            # Fallback to Type A (example is same as phrase or missing)
            distractors = _get_distractors(meaning, all_explanations)
            return _make_quiz(
                question=f'{p.phrase} 是什么意思？',
                correct_text=meaning,
                distractors=distractors,
            )


def _phrase_stage3_quiz(p: Phrase, idx: int, meaning: str, all_phrase_texts, all_explanations) -> LearnQuiz:
    """Generate a VARIED Stage 3 quiz for a phrase. Rotate through 3 types."""
    quiz_type = idx % 3
    example_en = p.example_1 or p.example_2 or p.example_3 or ""

    if not meaning:
        distractors = _get_distractors(p.phrase, all_phrase_texts)
        if example_en and p.phrase.lower() in example_en.lower():
            blanked = re.sub(re.escape(p.phrase), "______", example_en, flags=re.IGNORECASE)
            return _make_quiz(
                question=f'选择正确的短语填入空白处：\n{blanked}',
                correct_text=p.phrase,
                distractors=distractors,
            )
        return _make_quiz(
            question='请选择本次学习的正确短语',
            correct_text=p.phrase,
            distractors=distractors,
        )

    if quiz_type == 0:
        # Type A: 例句填空 — fill phrase into example sentence
        if example_en and p.phrase.lower() in example_en.lower():
            blanked = re.sub(re.escape(p.phrase), "______", example_en, flags=re.IGNORECASE)
            distractors = _get_distractors(p.phrase, all_phrase_texts)
            return _make_quiz(
                question=f'选择正确的短语填入空白处：\n{blanked}',
                correct_text=p.phrase,
                distractors=distractors,
                hint=meaning,
            )
        # Fallback
        distractors = _get_distractors(p.phrase, all_phrase_texts)
        return _make_quiz(
            question=f'「{meaning}」对应哪个英文短语？',
            correct_text=p.phrase,
            distractors=distractors,
        )

    elif quiz_type == 1:
        # Type B: 中文翻译选择 — show example English, pick correct Chinese translation
        example_en = p.example_1 or p.example_2 or ""
        example_cn = p.example_1_cn or p.example_2_cn or ""
        if example_en and example_cn:
            cn_pool = [e for e in all_explanations if e != meaning]
            distractors = _get_distractors(example_cn, cn_pool) if cn_pool else ["不知道", "不确定", "难以判断"]
            return _make_quiz(
                question=f'请选择下面这句话的正确翻译：\n{example_en}',
                correct_text=example_cn,
                distractors=distractors,
            )
        # Fallback
        distractors = _get_distractors(p.phrase, all_phrase_texts)
        return _make_quiz(
            question=f'「{meaning}」对应哪个英文短语？',
            correct_text=p.phrase,
            distractors=distractors,
        )

    else:
        # Type C: 反向匹配 — see Chinese, pick English phrase
        distractors = _get_distractors(p.phrase, all_phrase_texts)
        return _make_quiz(
            question=f'「{meaning}」对应哪个英文短语？',
            correct_text=p.phrase,
            distractors=distractors,
        )


# ---------------------------------------------------------------------------
# Word quiz builders — multiple quiz types
# ---------------------------------------------------------------------------

def _build_word_items(content: DailyContent, db: Session) -> list[LearnWordItem]:
    """Build word learning items with RICH, varied quizzes."""
    words = content.words
    if not words:
        return []

    all_words_db = db.query(Word).all()
    all_meanings = [w.meaning for w in all_words_db if w.meaning]
    all_word_texts = [w.word for w in all_words_db]
    all_phonetics = [w.phonetic for w in all_words_db if w.phonetic]

    items = []
    for idx, w in enumerate(words):
        stage2 = _word_stage2_quiz(w, idx, all_meanings, all_word_texts, all_phonetics)
        stage3 = _word_stage3_quiz(w, idx, all_meanings, all_word_texts)

        items.append(
            LearnWordItem(
                id=w.id,
                word=w.word,
                phonetic=w.phonetic,
                part_of_speech=w.part_of_speech,
                meaning=w.meaning or "",
                example=w.example,
                stage2_quiz=stage2,
                stage3_quiz=stage3,
            )
        )

    return items


def _word_stage2_quiz(w: Word, idx: int, all_meanings, all_word_texts, all_phonetics) -> LearnQuiz:
    """Generate a VARIED Stage 2 quiz for a word."""
    quiz_type = idx % 3

    if quiz_type == 0:
        # Type A: 看英选中 — see word, pick Chinese meaning
        distractors = _get_distractors(w.meaning or "", all_meanings)
        return _make_quiz(
            question=f'{w.word} 是什么意思？',
            correct_text=w.meaning or "",
            distractors=distractors,
        )

    elif quiz_type == 1:
        # Type B: 音标选词 — see phonetic, pick word
        if w.phonetic:
            distractors = _get_distractors(w.word, all_word_texts)
            return _make_quiz(
                question=f'音标 {w.phonetic} 对应哪个单词？',
                correct_text=w.word,
                distractors=distractors,
            )
        # Fallback to Type A
        distractors = _get_distractors(w.meaning or "", all_meanings)
        return _make_quiz(
            question=f'{w.word} 是什么意思？',
            correct_text=w.meaning or "",
            distractors=distractors,
        )

    else:
        # Type C: 看中选英 — see Chinese, pick English word
        distractors = _get_distractors(w.word, all_word_texts)
        return _make_quiz(
            question=f'哪个英文单词表示「{w.meaning}」？',
            correct_text=w.word,
            distractors=distractors,
        )


def _word_stage3_quiz(w: Word, idx: int, all_meanings, all_word_texts) -> LearnQuiz:
    """Generate a VARIED Stage 3 quiz for a word."""
    quiz_type = idx % 3

    if quiz_type == 0:
        # Type A: 例句选词 — fill word into example
        if w.example and w.word.lower() in w.example.lower():
            blanked = re.sub(re.escape(w.word), "______", w.example, count=1, flags=re.IGNORECASE)
            distractors = _get_distractors(w.word, all_word_texts)
            return _make_quiz(
                question=f'选择正确的单词填入空白处：\n{blanked}',
                correct_text=w.word,
                distractors=distractors,
                hint=w.meaning,
            )
        # Fallback
        distractors = _get_distractors(w.word, all_word_texts)
        return _make_quiz(
            question=f'「{w.meaning}」对应哪个英文单词？',
            correct_text=w.word,
            distractors=distractors,
        )

    elif quiz_type == 1:
        # Type B: 词性+释义 → 选单词
        pos_hint = f"（{w.part_of_speech}）" if w.part_of_speech else ""
        distractors = _get_distractors(w.word, all_word_texts)
        return _make_quiz(
            question=f'哪个单词的意思是「{w.meaning}」{pos_hint}？',
            correct_text=w.word,
            distractors=distractors,
        )

    else:
        # Type C: 看英选中 (different from stage 2)
        distractors = _get_distractors(w.meaning or "", all_meanings)
        return _make_quiz(
            question=f'单词 {w.word} 的中文意思是？',
            correct_text=w.meaning or "",
            distractors=distractors,
        )


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
