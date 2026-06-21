"""Shared helpers for compact word usage/context enrichment."""
import asyncio
import json
from typing import Optional

from sqlalchemy.orm import Session

from app.models.word import Word
from app.utils.ai_client import generate_word_enrichments

WORD_ENRICHMENT_BATCH_SIZE = 5


def parse_context_meanings(raw: Optional[str]) -> list[dict[str, str]]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []

    results = []
    for item in data:
        if not isinstance(item, dict):
            continue
        context = str(item.get("context") or "").strip()
        meaning = str(item.get("meaning") or "").strip()
        example = str(item.get("example") or "").strip()
        if not context or not meaning:
            continue
        entry = {"context": context, "meaning": meaning}
        if example:
            entry["example"] = example
        results.append(entry)
        if len(results) >= 2:
            break
    return results


async def ensure_word_enrichments(words: list[Word], db: Session) -> None:
    missing = [
        word for word in words
        if not word.usage_note and not parse_context_meanings(word.context_meanings)
    ]
    if not missing:
        return

    async def generate_batch(batch: list[Word]) -> dict[str, dict]:
        payload = [
            {
                "word": word.word,
                "part_of_speech": word.part_of_speech,
                "meaning": word.meaning,
                "example": word.example,
            }
            for word in batch
        ]

        try:
            return await generate_word_enrichments(payload)
        except Exception:
            return {}

    batches = [
        missing[start:start + WORD_ENRICHMENT_BATCH_SIZE]
        for start in range(0, len(missing), WORD_ENRICHMENT_BATCH_SIZE)
    ]
    batch_results = await asyncio.gather(*(generate_batch(batch) for batch in batches))

    enrichments = {}
    for result in batch_results:
        enrichments.update(result)

    updated = False
    for word in missing:
        entry = enrichments.get(word.word)
        if not entry:
            continue
        usage_note = (entry.get("usage_note") or "").strip()
        contexts = entry.get("context_meanings") or []
        if usage_note:
            word.usage_note = usage_note
            updated = True
        if contexts:
            word.context_meanings = json.dumps(contexts[:2], ensure_ascii=False)
            updated = True

    if updated:
        db.commit()
