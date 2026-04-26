"""Admin API - content import (called by Hermes cron)."""
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy.orm import Session
from datetime import date, timedelta
from app.database import get_db
from app.models.daily import DailyContent
from app.models.phrase import Phrase
from app.models.word import Word
from app.schemas.daily import ContentImport, ContentImportBatch
from app.config import get_settings

router = APIRouter()
settings = get_settings()


def verify_admin(api_key: str = Header(..., alias="X-API-Key")) -> str:
    """Verify admin API key."""
    if api_key != settings.ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key


def _upsert_content(db: Session, data: ContentImport):
    """Create or update one daily content payload by date."""
    existing = (
        db.query(DailyContent)
        .filter(DailyContent.date == data.date)
        .first()
    )

    if existing:
        existing.theme_zh = data.theme_zh
        existing.theme_en = data.theme_en
        existing.category = data.category
        existing.category_zh = data.category_zh
        existing.introduction = data.introduction
        existing.practice_tips = data.practice_tips
        existing.status = data.status or "scheduled"
        db.query(Phrase).filter(Phrase.content_id == existing.id).delete()
        db.query(Word).filter(Word.content_id == existing.id).delete()
        content = existing
    else:
        content = DailyContent(
            date=data.date,
            theme_zh=data.theme_zh,
            theme_en=data.theme_en,
            category=data.category,
            category_zh=data.category_zh,
            introduction=data.introduction,
            practice_tips=data.practice_tips,
            status=data.status or "scheduled",
        )
        db.add(content)
        db.flush()

    for i, p in enumerate(data.phrases):
        phrase = Phrase(
            content_id=content.id,
            phrase=p.phrase,
            meaning=p.meaning,
            explanation=p.explanation,
            example_1=p.examples[0].en if len(p.examples) > 0 else None,
            example_1_cn=p.examples[0].cn if len(p.examples) > 0 else None,
            example_2=p.examples[1].en if len(p.examples) > 1 else None,
            example_2_cn=p.examples[1].cn if len(p.examples) > 1 else None,
            example_3=p.examples[2].en if len(p.examples) > 2 else None,
            example_3_cn=p.examples[2].cn if len(p.examples) > 2 else None,
            source=p.source,
            sort_order=i,
        )
        db.add(phrase)

    for i, w in enumerate(data.words):
        word = Word(
            content_id=content.id,
            word=w.word,
            phonetic=w.phonetic,
            part_of_speech=w.part_of_speech,
            meaning=w.meaning,
            example=w.example,
            sort_order=i,
        )
        db.add(word)

    db.commit()
    db.refresh(content)

    return {
        "status": "ok",
        "content_id": content.id,
        "date": str(data.date),
        "category": data.category,
        "phrases": len(data.phrases),
        "words": len(data.words),
    }


@router.post("/content/import")
async def import_content(
    data: ContentImport,
    db: Session = Depends(get_db),
    _: str = Depends(verify_admin),
):
    """Import daily content from Hermes cron job. Upserts by date."""
    return _upsert_content(db, data)


@router.post("/content/import-batch")
async def import_content_batch(
    payload: ContentImportBatch,
    db: Session = Depends(get_db),
    _: str = Depends(verify_admin),
):
    """Batch import pre-generated daily content. Each item upserts by date."""
    if not payload.items:
        raise HTTPException(status_code=400, detail="items cannot be empty")

    results = []
    success = 0
    failed = 0
    for item in payload.items:
        try:
            result = _upsert_content(db, item)
            success += 1
            results.append({
                "date": str(item.date),
                "category": item.category,
                "status": "ok",
                "content_id": result["content_id"],
            })
        except Exception as exc:
            db.rollback()
            failed += 1
            results.append({
                "date": str(item.date),
                "category": item.category,
                "status": "failed",
                "error": str(exc),
            })

    return {
        "status": "ok" if failed == 0 else "partial",
        "batch_id": payload.batch_id,
        "total": len(payload.items),
        "success": success,
        "failed": failed,
        "items": results,
    }


@router.get("/content/inventory")
async def content_inventory(
    from_date: date = Query(None, alias="from"),
    days: int = Query(14, ge=1, le=90),
    db: Session = Depends(get_db),
    _: str = Depends(verify_admin),
):
    """Check future dated content stock for the requested date range."""
    start = from_date or date.today()
    expected_dates = [start + timedelta(days=i) for i in range(days)]
    end = expected_dates[-1]

    contents = (
        db.query(DailyContent)
        .filter(
            DailyContent.date >= start,
            DailyContent.date <= end,
        )
        .order_by(DailyContent.date.asc())
        .all()
    )
    by_date = {c.date: c for c in contents}
    items = []
    missing = []
    for d in expected_dates:
        c = by_date.get(d)
        if not c:
            missing.append(str(d))
            items.append({"date": str(d), "has_content": False})
        else:
            items.append({
                "date": str(d),
                "has_content": True,
                "content_id": c.id,
                "theme_zh": c.theme_zh,
                "theme_en": c.theme_en,
                "category": c.category,
                "category_zh": c.category_zh,
                "status": getattr(c, "status", "scheduled"),
                "phrases_count": len(c.phrases),
                "words_count": len(c.words),
            })

    return {
        "from": str(start),
        "to": str(end),
        "days": days,
        "available_count": len(contents),
        "missing_count": len(missing),
        "missing_dates": missing,
        "items": items,
    }


@router.get("/content/all")
async def list_all_content(
    db: Session = Depends(get_db),
    _: str = Depends(verify_admin),
):
    """Admin: list all content (for management)."""
    contents = (
        db.query(DailyContent)
        .order_by(DailyContent.date.desc())
        .all()
    )
    return [
        {
            "id": c.id,
            "date": str(c.date),
            "theme_zh": c.theme_zh,
            "theme_en": c.theme_en,
            "category": c.category,
            "category_zh": c.category_zh,
            "status": getattr(c, "status", "scheduled"),
            "phrase_count": len(c.phrases),
            "word_count": len(c.words),
        }
        for c in contents
    ]
