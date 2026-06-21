import asyncio
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

os.environ["DATABASE_URL"] = "sqlite:////private/tmp/easyspeak-distractor-upgrade-test.db"

import app.models  # noqa: F401
from app.database import Base, get_db
from app.models.daily import DailyContent
from app.models.distractor_cache import DistractorCache
from app.models.phrase import Phrase
from app.models.user import User
from app.models.word import Word
from app.routers import learn, quiz
from app.routers.auth import get_current_user
from app.schemas.quiz import QuizGenerateRequest
from app.utils.distractors import clean_distractors, get_challenging_distractors


class DistractorUpgradeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        cls.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine)
        Base.metadata.create_all(bind=cls.engine)

        app = FastAPI()
        app.include_router(learn.router, prefix="/api/v1/learn", tags=["learn"])
        app.include_router(quiz.router, prefix="/api/v1/quiz", tags=["quiz"])

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
        self._seed()

    def _seed(self):
        db = self.SessionLocal()
        db.add(User(openid="test-user"))
        content = DailyContent(id=1, date=date.today(), theme_zh="旅行", theme_en="Travel", category="travel", category_zh="旅行出行")
        db.add(content)
        db.flush()
        phrases = [
            Phrase(id=1, content_id=1, phrase="check in", meaning="办理入住", explanation="到达酒店后登记", example_1="We need to check in at the hotel.", example_1_cn="我们需要在酒店办理入住。"),
            Phrase(id=2, content_id=1, phrase="check out", meaning="退房", explanation="离开酒店时结账", example_1="We check out before noon.", example_1_cn="我们中午前退房。"),
            Phrase(id=3, content_id=1, phrase="book a room", meaning="预订房间", explanation="提前订房", example_1="I want to book a room.", example_1_cn="我想预订房间。"),
            Phrase(id=4, content_id=1, phrase="front desk", meaning="前台", explanation="酒店服务台", example_1="Ask the front desk.", example_1_cn="问前台。"),
        ]
        words = [
            Word(id=1, content_id=1, word="reservation", phonetic="/ˌrezəˈveɪʃn/", part_of_speech="n.", meaning="预订", example="I have a reservation.", usage_note="常用于酒店、餐厅或航班预订。", context_meanings=json.dumps([{"context": "酒店", "meaning": "预订记录", "example": "Your reservation is confirmed."}], ensure_ascii=False)),
            Word(id=2, content_id=1, word="reception", phonetic="/rɪˈsepʃn/", part_of_speech="n.", meaning="接待处", example="Go to reception."),
            Word(id=3, content_id=1, word="luggage", phonetic="/ˈlʌɡɪdʒ/", part_of_speech="n.", meaning="行李", example="Leave your luggage here."),
            Word(id=4, content_id=1, word="passport", phonetic="/ˈpɑːspɔːrt/", part_of_speech="n.", meaning="护照", example="Show your passport."),
        ]
        db.add_all(phrases + words)
        db.commit()
        db.close()

    def test_clean_distractors_filters_duplicates_answer_and_language(self):
        result = clean_distractors("预订", ["预订", "确认预订", "办理入住", "check in", "更改行程", "办理入住"], "zh")
        self.assertEqual(result, ["办理入住", "更改行程"])

    def test_challenging_distractors_use_cache_without_deepseek(self):
        db = self.SessionLocal()
        db.add(DistractorCache(cache_key="quiz_hard:v1:word_meaning_choice:1", distractors_json=json.dumps(["订座", "登记", "预约"], ensure_ascii=False)))
        db.commit()

        async def run():
            with patch("app.utils.distractors.generate_hard_distractors", new=AsyncMock(return_value=["不应调用"])) as mocked:
                distractors = await get_challenging_distractors(
                    db,
                    scope="quiz",
                    item_id=1,
                    question_type="word_meaning_choice",
                    correct="预订",
                    target_language="zh",
                    fallback_pool=["行李", "护照", "接待处"],
                )
            mocked.assert_not_awaited()
            return distractors

        self.assertEqual(asyncio.run(run()), ["订座", "登记", "预约"])
        db.close()

    def test_learn_session_falls_back_when_deepseek_unavailable(self):
        with patch("app.utils.distractors.generate_hard_distractors", new=AsyncMock(return_value=None)):
            response = self.client.post("/api/v1/learn/session", json={"content_id": 1, "learn_type": "word"})

        self.assertEqual(response.status_code, 200)
        item = response.json()["items"][0]
        self.assertEqual(len(item["stage2_quiz"]["options"]), 4)
        self.assertEqual(len(item["stage3_quiz"]["options"]), 4)

    def test_learn_session_does_not_block_on_ai_generation(self):
        with (
            patch("app.utils.word_enrichment.generate_word_enrichments", new=AsyncMock(return_value={})) as enrich_mock,
            patch("app.utils.distractors.generate_hard_distractors", new=AsyncMock(return_value=["不应调用"])) as distractor_mock,
        ):
            response = self.client.post("/api/v1/learn/session", json={"content_id": 1, "learn_type": "word"})

        self.assertEqual(response.status_code, 200)
        items = response.json()["items"]
        self.assertGreater(len(items), 0)
        self.assertEqual(len(items[0]["stage2_quiz"]["options"]), 4)
        self.assertEqual(len(items[0]["stage3_quiz"]["options"]), 4)
        enrich_mock.assert_not_awaited()
        distractor_mock.assert_not_awaited()

    def test_quiz_generates_new_word_question_types_and_balances_words(self):
        db = self.SessionLocal()
        user = db.query(User).first()

        async def run():
            with patch("app.utils.distractors.generate_hard_distractors", new=AsyncMock(return_value=None)):
                return await quiz.generate_quiz(
                    QuizGenerateRequest(mode="theme", question_count=8, category=["travel"]),
                    user=user,
                    db=db,
                )

        questions = asyncio.run(run())
        types = {question.question_type for question in questions}
        self.assertTrue({"word_meaning_choice", "meaning_to_word_choice", "word_context_choice"} & types)
        self.assertGreaterEqual(len([question for question in questions if question.item_type == "word"]), 3)
        for previous, current in zip(questions, questions[1:]):
            self.assertFalse(previous.question_type == current.question_type == questions[0].question_type)
        db.close()


if __name__ == "__main__":
    unittest.main()
