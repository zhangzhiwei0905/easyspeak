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
    meaning: Optional[str] = None
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
    theme_zh: str
    theme_en: str
    introduction: Optional[str] = None
    practice_tips: Optional[str] = None
    category: str
    category_zh: str
    status: str = "scheduled"


class DailyContentOut(DailyContentBase):
    id: int
    phrases: list[PhraseOut] = []
    words: list[WordOut] = []

    model_config = {"from_attributes": True}


class DailyContentListItem(BaseModel):
    id: int
    date: date
    theme_zh: str
    theme_en: str
    category: str
    category_zh: str
    phrase_count: int = 0
    word_count: int = 0

    model_config = {"from_attributes": True}


# --- Admin Import ---
class PhraseImport(BaseModel):
    phrase: str
    meaning: Optional[str] = None
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
    theme_zh: str
    theme_en: str
    category: str
    category_zh: str
    introduction: Optional[str] = None
    practice_tips: Optional[str] = None
    status: str = "scheduled"
    phrases: list[PhraseImport] = []
    words: list[WordImport] = []


class ContentImportBatch(BaseModel):
    batch_id: Optional[str] = None
    mode: str = "upsert"
    items: list[ContentImport]


# --- Today response (frontend expected format) ---
class ProgressInfo(BaseModel):
    phrases_learned: int = 0
    phrases_total: int = 0
    words_learned: int = 0
    words_total: int = 0


class ReviewInfo(BaseModel):
    due_count: int = 0


class TodayResponse(BaseModel):
    content: Optional[DailyContentOut] = None
    progress: ProgressInfo = ProgressInfo()
    review: ReviewInfo = ReviewInfo()


# --- Paginated response ---
class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    size: int
    pages: int

# --- Calendar response ---
class CalendarItem(BaseModel):
    date: date
    theme_zh: str
    has_content: bool = True

class CalendarResponse(BaseModel):
    year: int
    month: int
    items: list[CalendarItem]
