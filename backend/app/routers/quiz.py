"""Quiz system - generate questions, submit answers, track stats."""
import random
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from app.database import get_db
from app.models.user import User
from app.models.quiz import QuizRecord
from app.models.phrase import Phrase
from app.models.word import Word
from app.schemas.quiz import (
    QuizQuestion,
    QuizOption,
    QuizGenerateRequest,
    QuizSubmitRequest,
    QuizResult,
    QuizResultItem,
    QuizStats,
)
from app.routers.auth import get_current_user

router = APIRouter()


def _get_distractors(correct: str, all_items: list[str], count: int = 3) -> list[str]:
    """Get random distractors different from correct answer."""
    candidates = [item for item in all_items if item.lower() != correct.lower()]
    random.shuffle(candidates)
    return candidates[:count]


@router.post("/generate", response_model=list[QuizQuestion])
async def generate_quiz(
    request: QuizGenerateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate quiz questions."""
    questions = []

    if request.type in ("phrase", "mixed") and request.type != "fill_blank":
        phrase_query = db.query(Phrase)
        if request.content_id:
            phrase_query = phrase_query.filter(Phrase.content_id == request.content_id)
        phrases = phrase_query.all()
        all_meanings = [p.explanation[:50] for p in phrases]
        phrase_count = request.count // 2 if request.type == "mixed" else request.count
        selected = random.sample(phrases, min(phrase_count, len(phrases)))

        for p in selected:
            distractors = _get_distractors(p.explanation[:50], all_meanings)
            options = [p.explanation[:50]] + distractors
            random.shuffle(options)
            answer_key = chr(65 + options.index(p.explanation[:50]))

            questions.append(
                QuizQuestion(
                    question_id=p.id,
                    quiz_type="phrase_meaning",
                    question_text=f'"{p.phrase}" 是什么意思？',
                    options=[QuizOption(key=chr(65 + i), text=o) for i, o in enumerate(options)],
                    answer=answer_key,
                    item_type="phrase",
                )
            )

    if request.type in ("word", "mixed"):
        word_query = db.query(Word).filter(Word.phonetic.isnot(None))
        if request.content_id:
            word_query = word_query.filter(Word.content_id == request.content_id)
        words = word_query.all()
        all_words = [w.word for w in words]
        word_count = request.count // 2 if request.type == "mixed" else request.count
        selected = random.sample(words, min(word_count, len(words)))

        for w in selected:
            if not w.phonetic:
                continue
            distractors = _get_distractors(w.word, all_words)
            options = [w.word] + distractors
            random.shuffle(options)
            answer_key = chr(65 + options.index(w.word))

            questions.append(
                QuizQuestion(
                    question_id=w.id,
                    quiz_type="word_phonetic",
                    question_text=f'{w.phonetic} 对应哪个单词？',
                    options=[QuizOption(key=chr(65 + i), text=o) for i, o in enumerate(options)],
                    answer=answer_key,
                    item_type="word",
                )
            )

    # Fill-in-the-blank: pick phrases with examples, blank out the phrase from the example
    if request.type in ("fill_blank", "mixed"):
        phrase_query = db.query(Phrase)
        if request.content_id:
            phrase_query = phrase_query.filter(Phrase.content_id == request.content_id)
        all_phrases = phrase_query.all()

        # Only use phrases that have at least one example sentence
        phrases_with_examples = [
            p for p in all_phrases
            if p.example_1 or p.example_2 or p.example_3
        ]
        all_phrase_texts = [p.phrase for p in all_phrases]

        fill_count = request.count if request.type == "fill_blank" else max(request.count // 3, 1)
        if phrases_with_examples:
            selected = random.sample(
                phrases_with_examples, min(fill_count, len(phrases_with_examples))
            )

            for p in selected:
                # Pick a random available example
                examples = []
                if p.example_1:
                    examples.append(p.example_1)
                if p.example_2:
                    examples.append(p.example_2)
                if p.example_3:
                    examples.append(p.example_3)
                example = random.choice(examples)

                # Replace phrase with blank (case-insensitive)
                blanked = example.replace(p.phrase, "______")
                if blanked == example:
                    # Phrase not found literally — try lowercase
                    blanked = example.replace(p.phrase.lower(), "______")
                if blanked == example:
                    # Still no match, skip this phrase
                    continue

                distractors = _get_distractors(p.phrase, all_phrase_texts)
                options = [p.phrase] + distractors
                random.shuffle(options)
                answer_key = chr(65 + options.index(p.phrase))

                hint = p.explanation[:30] + "..." if len(p.explanation) > 30 else p.explanation

                questions.append(
                    QuizQuestion(
                        question_id=p.id,
                        quiz_type="fill_blank",
                        question_text=f'选择正确的短语填入空白处：\n"{blanked}"',
                        options=[QuizOption(key=chr(65 + i), text=o) for i, o in enumerate(options)],
                        answer=answer_key,
                        hint=hint,
                        item_type="phrase",
                    )
                )

    random.shuffle(questions)
    return questions[:request.count]


@router.post("/submit", response_model=QuizResult)
async def submit_quiz(
    request: QuizSubmitRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit quiz answers and get results."""
    details = []
    correct_count = 0

    # Build lookup: question_id -> correct answer info
    answer_lookup = {}
    for ans in request.answers:
        if ans.question_id in answer_lookup:
            continue

        quiz_type = ans.quiz_type or "phrase_meaning"

        # Try phrase
        phrase = db.query(Phrase).filter(Phrase.id == ans.question_id).first()
        if phrase:
            # Determine correct answer text based on quiz type
            if quiz_type == "fill_blank":
                correct_text = phrase.phrase
                question_text = f'选择正确的短语填入空白处'
            else:
                # phrase_meaning: correct answer is the explanation text
                correct_text = phrase.explanation[:50]
                question_text = f'"{phrase.phrase}" 是什么意思？'

            answer_lookup[ans.question_id] = {
                "quiz_type": quiz_type,
                "question_text": question_text,
                "correct_answer": correct_text,
            }
            continue

        # Try word
        word = db.query(Word).filter(Word.id == ans.question_id).first()
        if word:
            answer_lookup[ans.question_id] = {
                "quiz_type": quiz_type if quiz_type != "phrase_meaning" else "word_phonetic",
                "question_text": f'{word.phonetic or ""} 对应哪个单词？',
                "correct_answer": word.word,
            }

    for ans in request.answers:
        info = answer_lookup.get(ans.question_id, {
            "quiz_type": "unknown",
            "question_text": "",
            "correct_answer": "",
        })

        # Determine correctness: if the user's selected option matches the answer
        is_correct = (ans.answer == info["correct_answer"])

        if is_correct:
            correct_count += 1

        # Record to database
        record = QuizRecord(
            openid=user.openid,
            quiz_type=info["quiz_type"],
            question_id=ans.question_id,
            correct=is_correct,
        )
        db.add(record)

        # Get explanation/hint for wrong-answer review
        explanation = None
        phrase_obj = db.query(Phrase).filter(Phrase.id == ans.question_id).first()
        if phrase_obj:
            explanation = phrase_obj.explanation
        else:
            word_obj = db.query(Word).filter(Word.id == ans.question_id).first()
            if word_obj:
                explanation = f"{word_obj.word} ({word_obj.part_of_speech or ''}): {word_obj.meaning or ''}"

        details.append(
            QuizResultItem(
                question_id=ans.question_id,
                quiz_type=info["quiz_type"],
                question_text=info["question_text"],
                user_answer=ans.answer,
                correct_answer=info["correct_answer"],
                correct=is_correct,
                hint=explanation,
            )
        )

    db.commit()

    return QuizResult(
        total=len(request.answers),
        correct=correct_count,
        accuracy=correct_count / len(request.answers) if request.answers else 0,
        details=details,
    )


@router.get("/stats", response_model=QuizStats)
async def get_quiz_stats(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get quiz statistics for current user."""
    total = (
        db.query(func.count(QuizRecord.id))
        .filter(QuizRecord.openid == user.openid)
        .scalar()
        or 0
    )
    correct = (
        db.query(func.count(QuizRecord.id))
        .filter(QuizRecord.openid == user.openid, QuizRecord.correct == True)
        .scalar()
        or 0
    )

    # Calculate current and max streak
    records = (
        db.query(QuizRecord)
        .filter(QuizRecord.openid == user.openid)
        .order_by(QuizRecord.answered_at.desc())
        .limit(200)
        .all()
    )

    current_streak = 0
    max_streak = 0
    temp_streak = 0

    for r in records:
        if r.correct:
            temp_streak += 1
            max_streak = max(max_streak, temp_streak)
        else:
            temp_streak = 0

    # Recalculate current streak from most recent
    for r in records:
        if r.correct:
            current_streak += 1
        else:
            break

    return QuizStats(
        total_answered=total,
        total_correct=correct,
        accuracy=correct / total if total > 0 else 0,
        current_streak=current_streak,
        max_streak=max_streak,
    )
