import json
import os
import unittest
from datetime import date
from pathlib import Path
import sys
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["DATABASE_URL"] = "sqlite:////private/tmp/easyspeak-word-enrichment-test.db"

import app.models  # noqa: F401
from app.database import Base, get_db
from app.models.daily import DailyContent
from app.models.user import User
from app.models.word import Word
from app.routers import daily, learn
from app.routers.auth import get_current_user


class LearnWordEnrichmentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine)
        Base.metadata.create_all(bind=cls.engine)

        app = FastAPI()
        app.include_router(daily.router, prefix="/api/v1/daily", tags=["daily"])
        app.include_router(learn.router, prefix="/api/v1/learn", tags=["learn"])

        def override_get_db():
            db = cls.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        def override_get_current_user():
            db = cls.SessionLocal()
            try:
                return db.query(User).filter(User.openid == "test-user").first()
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_get_current_user
        cls.client = TestClient(app)

    def setUp(self):
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self._seed_data()

    def _seed_data(self):
        db = self.SessionLocal()
        db.add(User(openid="test-user"))
        db.add(
            DailyContent(
                id=1,
                date=date.today(),
                theme_zh="咖啡文化",
                theme_en="Coffee Culture",
                category="life",
                category_zh="生活场景",
            )
        )
        db.flush()
        db.add_all([
            Word(
                id=1,
                content_id=1,
                word="brew",
                phonetic="/bruː/",
                part_of_speech="v.",
                meaning="冲泡",
                example="I brew coffee every morning.",
            ),
            Word(
                id=2,
                content_id=1,
                word="aroma",
                phonetic="/əˈrəʊmə/",
                part_of_speech="n.",
                meaning="香气",
                example="The aroma filled the room.",
                usage_note="常用于描述食物、咖啡或花香。",
                context_meanings=json.dumps([
                    {
                        "context": "coffee",
                        "meaning": "咖啡散发出的香气",
                        "example": "The aroma of fresh coffee is comforting.",
                    }
                ], ensure_ascii=False),
            ),
        ])
        db.commit()
        db.close()

    def test_learn_session_uses_cached_word_enrichment_without_generating_missing_entries(self):
        enrichment = {
            "brew": {
                "usage_note": "常用于描述冲泡咖啡、茶，也可表示酝酿计划。",
                "context_meanings": [
                    {"context": "drink", "meaning": "冲泡饮品", "example": "She brews tea after lunch."},
                    {"context": "idea", "meaning": "酝酿想法", "example": "A plan is brewing."},
                ],
            }
        }

        with patch("app.utils.word_enrichment.generate_word_enrichments", new=AsyncMock(return_value=enrichment)) as mocked:
            response = self.client.post("/api/v1/learn/session", json={"content_id": 1, "learn_type": "word"})

        self.assertEqual(response.status_code, 200)
        words = response.json()["items"]
        brew = next(item for item in words if item["word"] == "brew")
        self.assertIsNone(brew["usage_note"])
        self.assertEqual(brew["context_meanings"], [])
        mocked.assert_not_awaited()

        db = self.SessionLocal()
        saved = db.query(Word).filter(Word.word == "brew").first()
        self.assertIsNone(saved.usage_note)
        self.assertIsNone(saved.context_meanings)
        db.close()

    def test_daily_today_uses_cached_word_enrichment_without_generating_missing_entries(self):
        enrichment = {
            "brew": {
                "usage_note": "常用于描述冲泡咖啡、茶，也可表示酝酿计划。",
                "context_meanings": [
                    {"context": "drink", "meaning": "冲泡饮品", "example": "She brews tea after lunch."},
                    {"context": "idea", "meaning": "酝酿想法", "example": "A plan is brewing."},
                ],
            }
        }

        with patch("app.utils.word_enrichment.generate_word_enrichments", new=AsyncMock(return_value=enrichment)) as mocked:
            response = self.client.get(f"/api/v1/daily/today?target_date={date.today().isoformat()}")

        self.assertEqual(response.status_code, 200)
        words = response.json()["content"]["words"]
        brew = next(item for item in words if item["word"] == "brew")
        aroma = next(item for item in words if item["word"] == "aroma")
        self.assertIsNone(brew["usage_note"])
        self.assertEqual(brew["context_meanings"], [])
        self.assertEqual(aroma["usage_note"], "常用于描述食物、咖啡或花香。")
        self.assertEqual(aroma["context_meanings"][0]["meaning"], "咖啡散发出的香气")
        mocked.assert_not_awaited()

        db = self.SessionLocal()
        saved = db.query(Word).filter(Word.word == "brew").first()
        self.assertIsNone(saved.usage_note)
        self.assertIsNone(saved.context_meanings)
        db.close()

    def test_daily_today_does_not_block_on_missing_word_enrichment(self):
        with patch("app.utils.word_enrichment.generate_word_enrichments", new=AsyncMock(return_value={})) as mocked:
            response = self.client.get(f"/api/v1/daily/today?target_date={date.today().isoformat()}")

        self.assertEqual(response.status_code, 200)
        words = response.json()["content"]["words"]
        brew = next(item for item in words if item["word"] == "brew")
        self.assertIsNone(brew["usage_note"])
        self.assertEqual(brew["context_meanings"], [])
        mocked.assert_not_awaited()

    def test_learn_session_uses_cached_word_enrichment_without_deepseek(self):
        db = self.SessionLocal()
        brew = db.query(Word).filter(Word.word == "brew").first()
        brew.usage_note = "常用于冲泡咖啡、茶。"
        brew.context_meanings = json.dumps([
            {"context": "drink", "meaning": "冲泡饮品", "example": "I brew coffee daily."}
        ], ensure_ascii=False)
        db.commit()
        db.close()

        with patch("app.utils.word_enrichment.generate_word_enrichments", new=AsyncMock(return_value={})) as mocked:
            response = self.client.post("/api/v1/learn/session", json={"content_id": 1, "learn_type": "word"})

        self.assertEqual(response.status_code, 200)
        words = response.json()["items"]
        aroma = next(item for item in words if item["word"] == "aroma")
        self.assertEqual(aroma["usage_note"], "常用于描述食物、咖啡或花香。")
        self.assertEqual(aroma["context_meanings"][0]["meaning"], "咖啡散发出的香气")
        mocked.assert_not_awaited()

    def test_daily_today_returns_quickly_when_many_words_are_missing_enrichment(self):
        db = self.SessionLocal()
        for i in range(3, 9):
            db.add(
                Word(
                    id=i,
                    content_id=1,
                    word=f"word{i}",
                    meaning=f"释义{i}",
                    example=f"Example {i}.",
                )
            )
        db.commit()
        db.close()

        async def fake_generate(payload):
            return {
                item["word"]: {
                    "usage_note": f"{item['word']} 的常见用法。",
                    "context_meanings": [
                        {"context": "daily", "meaning": "日常语境", "example": "A short example."}
                    ],
                }
                for item in payload
            }

        with patch("app.utils.word_enrichment.generate_word_enrichments", new=AsyncMock(side_effect=fake_generate)) as mocked:
            response = self.client.get(f"/api/v1/daily/today?target_date={date.today().isoformat()}")

        self.assertEqual(response.status_code, 200)
        mocked.assert_not_awaited()
        words = response.json()["content"]["words"]
        generated = next(item for item in words if item["word"] == "word8")
        self.assertEqual(generated["context_meanings"], [])


if __name__ == "__main__":
    unittest.main()
