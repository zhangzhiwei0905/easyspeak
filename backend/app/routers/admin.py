"""Admin API - content import (called by Hermes cron)."""
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from datetime import date
from app.database import get_db
from app.models.daily import DailyContent
from app.models.phrase import Phrase
from app.models.word import Word
from app.schemas.daily import ContentImport
from app.config import get_settings

router = APIRouter()
settings = get_settings()


def verify_admin(api_key: str = Header(..., alias="X-API-Key")) -> str:
    """Verify admin API key."""
    if api_key != settings.ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key


@router.post("/content/import")
async def import_content(
    data: ContentImport,
    db: Session = Depends(get_db),
    _: str = Depends(verify_admin),
):
    """
    Import daily content from Hermes cron job.
    Upserts by (date, time_slot).
    """
    # Check if exists
    existing = (
        db.query(DailyContent)
        .filter(DailyContent.date == data.date, DailyContent.time_slot == data.time_slot)
        .first()
    )

    if existing:
        # Update existing
        existing.theme_zh = data.theme_zh
        existing.theme_en = data.theme_en
        existing.introduction = data.introduction
        existing.practice_tips = data.practice_tips
        # Delete old phrases and words
        db.query(Phrase).filter(Phrase.content_id == existing.id).delete()
        db.query(Word).filter(Word.content_id == existing.id).delete()
        content = existing
    else:
        content = DailyContent(
            date=data.date,
            time_slot=data.time_slot,
            theme_zh=data.theme_zh,
            theme_en=data.theme_en,
            introduction=data.introduction,
            practice_tips=data.practice_tips,
        )
        db.add(content)
        db.flush()  # get content.id

    # Add phrases
    for i, p in enumerate(data.phrases):
        phrase = Phrase(
            content_id=content.id,
            phrase=p.phrase,
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

    # Add words
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

    return {
        "status": "ok",
        "content_id": content.id,
        "date": str(data.date),
        "time_slot": data.time_slot,
        "phrases": len(data.phrases),
        "words": len(data.words),
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
            "time_slot": c.time_slot,
            "theme_zh": c.theme_zh,
            "theme_en": c.theme_en,
            "phrase_count": len(c.phrases),
            "word_count": len(c.words),
        }
        for c in contents
    ]
