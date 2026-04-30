"""User profile and achievements API."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timezone
from app.database import get_db
from app.models.user import User, UserProgress, UserAchievement
from app.models.quiz import QuizRecord
from app.models.learn_session import LearnSession
from app.routers.auth import get_current_user

router = APIRouter()

ACHIEVEMENTS = [
    # Learning Growth
    {"id": "first_learn", "name": "初学者", "icon": "🌟", "desc": "完成首次学习", "category": "learning", "category_zh": "学习成长"},
    {"id": "learn_10",   "name": "学习新秀", "icon": "📘", "desc": "累计完成10次学习", "category": "learning", "category_zh": "学习成长"},
    {"id": "learn_30",   "name": "学习达人", "icon": "📚", "desc": "累计完成30次学习", "category": "learning", "category_zh": "学习成长"},
    # Streak
    {"id": "streak_3",   "name": "3日打卡", "icon": "🔥", "desc": "连续学习3天", "category": "streak", "category_zh": "连续打卡"},
    {"id": "streak_7",   "name": "7日打卡", "icon": "📅", "desc": "连续学习7天", "category": "streak", "category_zh": "连续打卡"},
    {"id": "streak_14",  "name": "14日打卡", "icon": "⚡", "desc": "连续学习14天", "category": "streak", "category_zh": "连续打卡"},
    {"id": "streak_30",  "name": "学习狂人", "icon": "💪", "desc": "连续学习30天", "category": "streak", "category_zh": "连续打卡"},
    # Word Master
    {"id": "word_10",    "name": "初识单词", "icon": "🔤", "desc": "掌握10个单词", "category": "word", "category_zh": "单词大师"},
    {"id": "word_50",    "name": "单词达人", "icon": "📖", "desc": "掌握50个单词", "category": "word", "category_zh": "单词大师"},
    {"id": "word_100",   "name": "百词斩",   "icon": "🎯", "desc": "掌握100个单词", "category": "word", "category_zh": "单词大师"},
    # Phrase Expert
    {"id": "phrase_10",  "name": "初识短语", "icon": "💬", "desc": "掌握10个短语", "category": "phrase", "category_zh": "短语达人"},
    {"id": "phrase_30",  "name": "短语达人", "icon": "🗣️", "desc": "掌握30个短语", "category": "phrase", "category_zh": "短语达人"},
    {"id": "phrase_50",  "name": "短语收藏家", "icon": "🏆", "desc": "掌握50个短语", "category": "phrase", "category_zh": "短语达人"},
    # Quiz Champion
    {"id": "quiz_20",    "name": "初试身手", "icon": "✏️", "desc": "累计答题20道", "category": "quiz", "category_zh": "答题高手"},
    {"id": "quiz_100",   "name": "答题达人", "icon": "🎖️", "desc": "累计答题100道", "category": "quiz", "category_zh": "答题高手"},
    {"id": "quiz_500",   "name": "答题高手", "icon": "👑", "desc": "累计答题500道", "category": "quiz", "category_zh": "答题高手"},
    {"id": "quiz_accuracy", "name": "精准答题", "icon": "🎯", "desc": "答题正确率≥80%", "category": "quiz", "category_zh": "答题高手"},
]


def _check_achievements(user: User, db: Session) -> dict[str, bool]:
    """Evaluate all achievement conditions against current user stats.
    Returns a dict of {achievement_id: is_unlocked}.
    """
    # Gather stats
    total_learns = db.query(func.count(LearnSession.id)).filter(
        LearnSession.openid == user.openid
    ).scalar() or 0

    streak = user.study_streak or 0

    mastered_words = db.query(func.count(UserProgress.id)).filter(
        UserProgress.openid == user.openid,
        UserProgress.word_id.isnot(None),
        UserProgress.mastery >= 4,
    ).scalar() or 0

    mastered_phrases = db.query(func.count(UserProgress.id)).filter(
        UserProgress.openid == user.openid,
        UserProgress.phrase_id.isnot(None),
        UserProgress.mastery >= 4,
    ).scalar() or 0

    total_quiz = db.query(func.count(QuizRecord.id)).filter(
        QuizRecord.openid == user.openid
    ).scalar() or 0

    correct_quiz = db.query(func.count(QuizRecord.id)).filter(
        QuizRecord.openid == user.openid,
        QuizRecord.correct == True,
    ).scalar() or 0

    accuracy = (correct_quiz / total_quiz * 100) if total_quiz > 0 else 0

    # Evaluate each achievement
    results = {}
    for ach in ACHIEVEMENTS:
        aid = ach["id"]
        if aid == "first_learn":
            results[aid] = total_learns >= 1
        elif aid == "learn_10":
            results[aid] = total_learns >= 10
        elif aid == "learn_30":
            results[aid] = total_learns >= 30
        elif aid == "streak_3":
            results[aid] = streak >= 3
        elif aid == "streak_7":
            results[aid] = streak >= 7
        elif aid == "streak_14":
            results[aid] = streak >= 14
        elif aid == "streak_30":
            results[aid] = streak >= 30
        elif aid == "word_10":
            results[aid] = mastered_words >= 10
        elif aid == "word_50":
            results[aid] = mastered_words >= 50
        elif aid == "word_100":
            results[aid] = mastered_words >= 100
        elif aid == "phrase_10":
            results[aid] = mastered_phrases >= 10
        elif aid == "phrase_30":
            results[aid] = mastered_phrases >= 30
        elif aid == "phrase_50":
            results[aid] = mastered_phrases >= 50
        elif aid == "quiz_20":
            results[aid] = total_quiz >= 20
        elif aid == "quiz_100":
            results[aid] = total_quiz >= 100
        elif aid == "quiz_500":
            results[aid] = total_quiz >= 500
        elif aid == "quiz_accuracy":
            results[aid] = total_quiz >= 20 and accuracy >= 80

    return results


@router.get("/achievements")
async def get_achievements(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all achievements with unlock status. Newly unlocked ones are persisted."""
    now = datetime.now(timezone.utc)

    # Already persisted achievements
    existing_rows = db.query(UserAchievement).filter(
        UserAchievement.openid == user.openid
    ).all()
    persisted = {row.achievement_id: row.unlocked_at for row in existing_rows}

    # Evaluate current conditions
    unlocked = _check_achievements(user, db)

    # Persist newly unlocked ones
    new_unlocks = False
    for ach in ACHIEVEMENTS:
        aid = ach["id"]
        if unlocked.get(aid) and aid not in persisted:
            db.add(UserAchievement(openid=user.openid, achievement_id=aid, unlocked_at=now))
            persisted[aid] = now
            new_unlocks = True

    if new_unlocks:
        db.commit()

    # Build response
    result = []
    for ach in ACHIEVEMENTS:
        aid = ach["id"]
        is_unlocked = unlocked.get(aid, False)
        unlocked_at = persisted.get(aid)
        result.append({
            "id": aid,
            "name": ach["name"],
            "icon": ach["icon"],
            "desc": ach["desc"],
            "category": ach["category"],
            "category_zh": ach["category_zh"],
            "unlocked": is_unlocked,
            "unlocked_at": unlocked_at.isoformat() if unlocked_at else None,
        })

    return {"achievements": result}
