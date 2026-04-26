"""Shared helpers for brief phrase meaning display."""

from typing import Optional

from app.models.phrase import Phrase

_SENTENCE_PUNCTUATION = ("。", "！", "？", "；", "：", ".", "!", "?", ";", ":")
_MAX_BRIEF_CHARS = 16


def _clean_text(text: Optional[str]) -> str:
    return " ".join((text or "").strip().split())


def _is_brief_candidate(text: str) -> bool:
    if not text:
        return False
    if len(text) > _MAX_BRIEF_CHARS:
        return False
    return not any(punctuation in text for punctuation in _SENTENCE_PUNCTUATION)


def get_phrase_short_meaning(phrase: Phrase) -> Optional[str]:
    """Return a short meaning suitable for quiz options, or None when unavailable."""
    meaning = _clean_text(phrase.meaning)
    if meaning:
        return meaning

    for candidate in (phrase.example_1_cn, phrase.example_2_cn):
        cleaned = _clean_text(candidate)
        if _is_brief_candidate(cleaned):
            return cleaned

    return None


def get_phrase_learning_explanation(phrase: Phrase) -> str:
    """Return the richer explanation used in learning cards and answer feedback."""
    explanation = _clean_text(phrase.explanation)
    if explanation:
        return explanation

    meaning = get_phrase_short_meaning(phrase)
    return meaning or phrase.phrase
