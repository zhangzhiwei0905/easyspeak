"""Shared distractor generation and caching helpers."""

import json
import re
from typing import Optional

from sqlalchemy.orm import Session

from app.models.distractor_cache import DistractorCache
from app.utils.ai_client import generate_hard_distractors

CACHE_VERSION = "v1"


def contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", text or ""))


def normalize_text(text: str) -> str:
    return re.sub(r"[^\w\s\u3400-\u9fff]", "", (text or "").strip().lower())


def cache_key(scope: str, item_id: int, question_type: str) -> str:
    return DistractorCache.make_key(f"{scope}_hard:{CACHE_VERSION}:{question_type}", item_id)


def clean_distractors(correct: str, distractors: list[str], target_language: Optional[str] = None, count: int = 3) -> list[str]:
    correct_raw = (correct or "").strip()
    correct_key = normalize_text(correct_raw)
    results = []
    seen = {correct_key}

    for item in distractors or []:
        value = str(item or "").strip()
        key = normalize_text(value)
        if not value or not key or key in seen:
            continue
        if correct_key and (key in correct_key or correct_key in key):
            continue
        if target_language == "zh" and not contains_cjk(value):
            continue
        if target_language == "en" and contains_cjk(value):
            continue
        seen.add(key)
        results.append(value)
        if len(results) >= count:
            break
    return results


def read_cached_distractors(db: Session, key: str, correct: str, target_language: Optional[str] = None, count: int = 3) -> Optional[list[str]]:
    entry = db.query(DistractorCache).filter(DistractorCache.cache_key == key).first()
    if not entry or entry.is_expired():
        return None
    try:
        raw = json.loads(entry.distractors_json)
    except (json.JSONDecodeError, TypeError):
        return None
    cleaned = clean_distractors(correct, raw, target_language, count)
    return cleaned if len(cleaned) >= count else None


def write_cached_distractors(db: Session, key: str, distractors: list[str]) -> None:
    payload = json.dumps(distractors, ensure_ascii=False)
    entry = db.query(DistractorCache).filter(DistractorCache.cache_key == key).first()
    if entry:
        entry.distractors_json = payload
    else:
        db.add(DistractorCache(cache_key=key, distractors_json=payload))


def fallback_distractors(correct: str, pool: list[str], target_language: Optional[str] = None, count: int = 3) -> list[str]:
    return clean_distractors(correct, pool, target_language, count)


async def get_challenging_distractors(
    db: Session,
    *,
    scope: str,
    item_id: int,
    question_type: str,
    correct: str,
    target_language: Optional[str],
    fallback_pool: list[str],
    prompt: str = "",
    item_text: str = "",
    meaning: str = "",
    part_of_speech: str = "",
    example: str = "",
    count: int = 3,
    allow_ai: bool = True,
) -> list[str]:
    key = cache_key(scope, item_id, question_type)
    if db is not None and hasattr(db, "query"):
        cached = read_cached_distractors(db, key, correct, target_language, count)
        if cached:
            return cached

    if not allow_ai:
        return fallback_distractors(correct, fallback_pool, target_language, count)

    generated = await generate_hard_distractors(
        question_type=question_type,
        correct=correct,
        target_language=target_language or "auto",
        prompt=prompt,
        item_text=item_text,
        meaning=meaning,
        part_of_speech=part_of_speech,
        example=example,
        candidates=fallback_pool[:20],
        count=count,
    )
    cleaned = clean_distractors(correct, generated or [], target_language, count)
    if len(cleaned) >= count:
        write_cached_distractors(db, key, cleaned)
        return cleaned

    return fallback_distractors(correct, fallback_pool, target_language, count)
