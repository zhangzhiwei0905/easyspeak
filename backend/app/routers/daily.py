"""Daily content API - browse today's and historical content."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from datetime import date
from app.database import get_db
from app.models.daily import DailyContent
from app.schemas.daily import DailyContentOut, DailyContentListItem, PaginatedResponse

router = APIRouter()


@router.get("/today", response_model=list[DailyContentOut])
async def get_today(db: Session = Depends(get_db)):
    """Get today's push content (morning + evening)."""
    today = date.today()
    contents = (
        db.query(DailyContent)
        .options(joinedload(DailyContent.phrases), joinedload(DailyContent.words))
        .filter(DailyContent.date == today)
        .order_by(DailyContent.time_slot)
        .all()
    )
    return contents


@router.get("/date/{target_date}", response_model=list[DailyContentOut])
async def get_by_date(target_date: date, db: Session = Depends(get_db)):
    """Get content for a specific date."""
    contents = (
        db.query(DailyContent)
        .options(joinedload(DailyContent.phrases), joinedload(DailyContent.words))
        .filter(DailyContent.date == target_date)
        .order_by(DailyContent.time_slot)
        .all()
    )
    if not contents:
        raise HTTPException(status_code=404, detail=f"No content found for {target_date}")
    return contents


@router.get("/list", response_model=PaginatedResponse)
async def get_list(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Paginated list of all daily content."""
    from sqlalchemy import func

    total = db.query(func.count(DailyContent.id)).scalar()
    contents = (
        db.query(DailyContent)
        .order_by(DailyContent.date.desc(), DailyContent.time_slot)
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )

    items = []
    for c in contents:
        items.append(
            DailyContentListItem(
                id=c.id,
                date=c.date,
                time_slot=c.time_slot,
                theme_zh=c.theme_zh,
                theme_en=c.theme_en,
                phrase_count=len(c.phrases),
                word_count=len(c.words),
            )
        )

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        size=size,
        pages=(total + size - 1) // size,
    )


@router.get("/themes", response_model=list[str])
async def get_themes(db: Session = Depends(get_db)):
    """Get all unique themes for search/filter."""
    themes = (
        db.query(DailyContent.theme_zh)
        .distinct()
        .order_by(DailyContent.date.desc())
        .all()
    )
    return [t[0] for t in themes]


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
    db: Session = Depends(get_db),
):
    """Full-text search across phrases, words, and themes."""
    from app.models.phrase import Phrase
    from app.models.word import Word

    keyword = f"%{q}%"

    phrase_results = (
        db.query(Phrase)
        .join(DailyContent)
        .filter(Phrase.phrase.like(keyword))
        .limit(20)
        .all()
    )

    word_results = (
        db.query(Word)
        .join(DailyContent)
        .filter(Word.word.like(keyword) | Word.meaning.like(keyword))
        .limit(20)
        .all()
    )

    return {
        "query": q,
        "phrases": [
            {
                "id": p.id,
                "phrase": p.phrase,
                "theme": p.content.theme_zh,
                "date": str(p.content.date),
            }
            for p in phrase_results
        ],
        "words": [
            {
                "id": w.id,
                "word": w.word,
                "phonetic": w.phonetic,
                "meaning": w.meaning,
                "theme": w.content.theme_zh,
                "date": str(w.content.date),
            }
            for w in word_results
        ],
    }
