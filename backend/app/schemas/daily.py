"""Pydantic schemas for daily content."""
from pydantic import BaseModel, model_validator
from typing import Optional
from datetime import date


# --- Phrases ---
class PhraseExample(BaseModel):
    en: str
    cn: str


class PhraseBase(BaseModel):
    phrase: str
    explanation: str
    examples: list[PhraseExample] = []
    source: Optional[str] = None
    sort_order: int = 0


class PhraseOut(PhraseBase):
    id: int
    content_id: int

    # Flat columns from ORM (used internally for validation, excluded from API output)
    example_1: Optional[str] = None
    example_1_cn: Optional[str] = None
    example_2: Optional[str] = None
    example_2_cn: Optional[str] = None
    example_3: Optional[str] = None
    example_3_cn: Optional[str] = None

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def build_examples(cls, values):
        """Convert flat example columns into examples list."""
        if isinstance(values, dict) and not values.get("examples"):
            examples = []
            for i in range(1, 4):
                en = values.get(f"example_{i}")
                cn = values.get(f"example_{i}_cn")
                if en:
                    examples.append({"en": en, "cn": cn or ""})
            values["examples"] = examples
        return values


# --- Words ---
class WordBase(BaseModel):
    word: str
    phonetic: Optional[str] = None
    part_of_speech: Optional[str] = None
    meaning: Optional[str] = None
    example: Optional[str] = None
    sort_order: int = 0


class WordOut(WordBase):
    id: int
    content_id: int

    model_config = {"from_attributes": True}


# --- Daily Content ---
class DailyContentBase(BaseModel):
    date: date
    time_slot: str
    theme_zh: str
    theme_en: str
    introduction: Optional[str] = None
    practice_tips: Optional[str] = None


class DailyContentOut(DailyContentBase):
    id: int
    phrases: list[PhraseOut] = []
    words: list[WordOut] = []

    model_config = {"from_attributes": True}


class DailyContentListItem(BaseModel):
    id: int
    date: date
    time_slot: str
    theme_zh: str
    theme_en: str
    phrase_count: int = 0
    word_count: int = 0

    model_config = {"from_attributes": True}


# --- Admin Import ---
class PhraseImport(BaseModel):
    phrase: str
    explanation: str
    examples: list[PhraseExample] = []
    source: Optional[str] = None


class WordImport(BaseModel):
    word: str
    phonetic: Optional[str] = None
    part_of_speech: Optional[str] = None
    meaning: Optional[str] = None
    example: Optional[str] = None


class ContentImport(BaseModel):
    date: date
    time_slot: str
    theme_zh: str
    theme_en: str
    introduction: Optional[str] = None
    practice_tips: Optional[str] = None
    phrases: list[PhraseImport] = []
    words: list[WordImport] = []


# --- Paginated response ---
class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    size: int
    pages: int
