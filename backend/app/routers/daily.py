"""Daily content API - browse today's and historical content."""
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Optional
from jose import jwt
from app.config import get_settings
from app.database import get_db
from app.models.daily import DailyContent
from app.models.user import User
from app.schemas.daily import DailyContentOut, DailyContentListItem, PaginatedResponse, TodayResponse, CalendarResponse, CalendarItem

router = APIRouter()
settings = get_settings()

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


def _build_content_list_item(c):
    return DailyContentListItem(
        id=c.id,
        date=c.date,
        theme_zh=c.theme_zh,
        theme_en=c.theme_en,
        category=c.category,
        category_zh=c.category_zh,
        phrase_count=len(c.phrases),
        word_count=len(c.words),
    )


def _today_shanghai():
    """Return today's date in China timezone so daily content switches at local midnight."""
    return datetime.now(ZoneInfo("Asia/Shanghai")).date()


def _visible_before_date():
    """Return the latest date visible in content library.

    Simulates a 9:00 AM daily push: before 9 AM, today's content is hidden;
    at/after 9 AM, today's content becomes visible.
    """
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    return now.date() if now.hour >= 9 else now.date() - timedelta(days=1)


def _visible_content_filter(query):
    """Hide disabled content AND future/unpushed content.

    Content with date > visible_before_date is not yet "pushed" and should
    not appear in library listings or search results.
    """
    visible_before = _visible_before_date()
    filters = [DailyContent.date <= visible_before]
    if hasattr(DailyContent, "status"):
        filters.append(DailyContent.status != "hidden")
    return query.filter(*filters)


async def get_optional_user(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Return the current user when a valid token is present; allow anonymous reads."""
    if not authorization:
        return None

    token = authorization.replace("Bearer ", "") if authorization.startswith("Bearer ") else authorization
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        openid = payload.get("sub")
    except Exception:
        return None

    if not openid:
        return None
    return db.query(User).filter(User.openid == openid).first()


def _build_today_response(content, db=None, openid=None):
    """Build TodayResponse from a single DailyContent."""
    progress = {}
    review = {}

    if db and openid and content:
        from app.models.user import UserProgress
        from sqlalchemy import func

        phrase_ids = [p.id for p in content.phrases]
        word_ids = [w.id for w in content.words]

        learned_phrases = (
            db.query(func.count(UserProgress.id))
            .filter(UserProgress.openid == openid, UserProgress.phrase_id.in_(phrase_ids))
            .scalar()
        ) if phrase_ids else 0

        learned_words = (
            db.query(func.count(UserProgress.id))
            .filter(UserProgress.openid == openid, UserProgress.word_id.in_(word_ids))
            .scalar()
        ) if word_ids else 0

        progress = {
            "phrases_learned": learned_phrases,
            "phrases_total": len(phrase_ids),
            "words_learned": learned_words,
            "words_total": len(word_ids),
        }

    if openid:
        from app.models.user import UserProgress
        from sqlalchemy import func

        due_count = (
            db.query(func.count(UserProgress.id))
            .filter(UserProgress.openid == openid, UserProgress.next_review <= func.now())
            .scalar()
        )
        review = {"due_count": due_count}

    return TodayResponse(content=content, progress=progress, review=review)


@router.get("/today", response_model=TodayResponse)
async def get_today(
    target_date: date = Query(None, description="日期，默认今天"),
    user: Optional[User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """Get today's push content."""
    target = target_date or _today_shanghai()
    query = (
        db.query(DailyContent)
        .options(joinedload(DailyContent.phrases), joinedload(DailyContent.words))
        .filter(DailyContent.date == target)
    )
    content = _visible_content_filter(query).first()
    return _build_today_response(content, db, user.openid if user else None)


@router.get("/date/{target_date}", response_model=TodayResponse)
async def get_by_date(target_date: date, db: Session = Depends(get_db)):
    """Get content for a specific date."""
    query = (
        db.query(DailyContent)
        .options(joinedload(DailyContent.phrases), joinedload(DailyContent.words))
        .filter(DailyContent.date == target_date)
    )
    content = _visible_content_filter(query).first()
    if not content:
        raise HTTPException(status_code=404, detail=f"No content found for {target_date}")
    return _build_today_response(content, db)


@router.get("/list", response_model=PaginatedResponse)
async def get_list(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=50),
    category: Optional[str] = Query(None, description="主题类型"),
    db: Session = Depends(get_db),
):
    """Paginated list of all daily content."""
    query = _visible_content_filter(db.query(DailyContent)).order_by(DailyContent.date.desc())

    if category:
        query = query.filter(DailyContent.category == category)

    total = query.count()
    contents = query.offset((page - 1) * size).limit(size).all()

    items = [_build_content_list_item(c) for c in contents]

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        size=size,
        pages=(total + size - 1) // size,
    )


@router.get("/calendar", response_model=CalendarResponse)
async def get_calendar(
    year: int = Query(..., ge=2000),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
):
    """Get calendar data with themes for a specific year and month."""
    from sqlalchemy import and_
    import datetime
    import calendar

    _, last_day = calendar.monthrange(year, month)
    start_date = datetime.date(year, month, 1)
    end_date = datetime.date(year, month, last_day)

    # Don't show future dates beyond today's push
    visible_before = _visible_before_date()
    if end_date > visible_before:
        end_date = visible_before

    if start_date > end_date:
        # Entire month is in the future
        return CalendarResponse(year=year, month=month, items=[])

    contents = (
        db.query(DailyContent.date, DailyContent.theme_zh)
        .filter(and_(DailyContent.date >= start_date, DailyContent.date <= end_date))
        .order_by(DailyContent.date.asc())
        .all()
    )

    items_dict = {}
    for c in contents:
        if c.date not in items_dict:
            items_dict[c.date] = CalendarItem(date=c.date, theme_zh=c.theme_zh, has_content=True)

    return CalendarResponse(
        year=year,
        month=month,
        items=list(items_dict.values())
    )


@router.get("/themes", response_model=list[str])
async def get_themes(db: Session = Depends(get_db)):
    """Get all unique themes for search/filter (only visible content)."""
    visible_before = _visible_before_date()
    themes = (
        db.query(DailyContent.theme_zh)
        .filter(DailyContent.date <= visible_before)
        .distinct()
        .order_by(DailyContent.date.desc())
        .all()
    )
    return [t[0] for t in themes]


@router.get("/categories")
async def get_categories():
    """Get all supported theme categories."""
    return [{"key": key, "label": label} for key, label in CATEGORY_LABELS.items()]


@router.get("/content/{content_id}", response_model=DailyContentOut)
async def get_content(content_id: int, db: Session = Depends(get_db)):
    """Get full content for a specific push (phrases + words)."""
    content = (
        db.query(DailyContent)
        .options(joinedload(DailyContent.phrases), joinedload(DailyContent.words))
        .filter(DailyContent.id == content_id)
        .first()
    )
    if not content:
        raise HTTPException(status_code=404, detail="Content not found")
    return content


@router.get("/search")
async def search(
    q: str = Query(..., min_length=1),
    category: Optional[str] = Query(None, description="主题类型"),
    db: Session = Depends(get_db),
):
    """Full-text search across phrases, words, and themes."""
    from app.models.phrase import Phrase
    from app.models.word import Word

    keyword = f"%{q}%"
    visible_before = _visible_before_date()

    base_filters = [
        DailyContent.date <= visible_before,
        DailyContent.status != "hidden",
    ]

    phrase_query = (
        db.query(Phrase)
        .join(DailyContent)
        .filter(
            (Phrase.phrase.like(keyword) | Phrase.meaning.like(keyword)),
            *base_filters,
        )
    )
    word_query = (
        db.query(Word)
        .join(DailyContent)
        .filter(
            (Word.word.like(keyword) | Word.meaning.like(keyword)),
            *base_filters,
        )
    )
    theme_query = (
        db.query(DailyContent)
        .filter(
            DailyContent.theme_zh.like(keyword) | DailyContent.theme_en.like(keyword),
            *base_filters,
        )
        .order_by(DailyContent.date.desc())
    )

    if category:
        phrase_query = phrase_query.filter(DailyContent.category == category)
        word_query = word_query.filter(DailyContent.category == category)
        theme_query = theme_query.filter(DailyContent.category == category)

    phrase_results = phrase_query.limit(20).all()
    word_results = word_query.limit(20).all()
    theme_results = theme_query.limit(20).all()

    return {
        "query": q,
        "themes": [
            {
                "id": t.id,
                "content_id": t.id,
                "theme_zh": t.theme_zh,
                "theme_en": t.theme_en,
                "date": str(t.date),
                "category": t.category,
                "category_zh": t.category_zh,
            }
            for t in theme_results
        ],
        "phrases": [
            {
                "id": p.id,
                "content_id": p.content_id,
                "phrase": p.phrase,
                "meaning": p.meaning or "",
                "theme": p.content.theme_zh,
                "date": str(p.content.date),
                "category": p.content.category,
            }
            for p in phrase_results
        ],
        "words": [
            {
                "id": w.id,
                "content_id": w.content_id,
                "word": w.word,
                "phonetic": w.phonetic,
                "meaning": w.meaning,
                "theme": w.content.theme_zh,
                "date": str(w.content.date),
                "category": w.content.category,
            }
            for w in word_results
        ],
    }
