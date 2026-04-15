"""Batch import historical Obsidian data into the database."""
import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from typing import Optional
from app.database import SessionLocal, engine, Base
from app.models.daily import DailyContent
from app.models.phrase import Phrase
from app.models.word import Word
from app.utils.obsidian_parser import parse_all_obsidian_files
from app.schemas.daily import ContentImport


def import_all(obsidian_dir: Optional[str] = None):
    """Import all Obsidian files into the database."""
    if obsidian_dir is None:
        from app.config import get_settings
        settings = get_settings()
        obsidian_dir = settings.OBSIDIAN_DATA_PATH

    # Create tables
    Base.metadata.create_all(bind=engine)

    print(f"📂 Scanning: {obsidian_dir}")
    contents = parse_all_obsidian_files(obsidian_dir)

    if not contents:
        print("No files found or parsed.")
        return

    db = SessionLocal()
    imported = 0
    skipped = 0

    for data in contents:
        # Check if already exists
        existing = (
            db.query(DailyContent)
            .filter(DailyContent.date == data.date, DailyContent.time_slot == data.time_slot)
            .first()
        )

        if existing:
            print(f"  ⏭️  Skip (exists): {data.date} {data.time_slot} - {data.theme_zh}")
            skipped += 1
            continue

        # Create content
        content = DailyContent(
            date=data.date,
            time_slot=data.time_slot,
            theme_zh=data.theme_zh,
            theme_en=data.theme_en,
            introduction=data.introduction,
            practice_tips=data.practice_tips,
        )
        db.add(content)
        db.flush()

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

        print(f"  ✅ Imported: {data.date} {data.time_slot} - {data.theme_zh}")
        imported += 1

    db.commit()
    db.close()

    print(f"\n📊 Done! Imported: {imported}, Skipped: {skipped}")


if __name__ == "__main__":
    custom_dir = sys.argv[1] if len(sys.argv) > 1 else None
    import_all(custom_dir)
