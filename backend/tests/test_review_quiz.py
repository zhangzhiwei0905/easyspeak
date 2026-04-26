import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.models  # noqa: F401
from app.database import Base, get_db
from app.models.daily import DailyContent
from app.models.phrase import Phrase
from app.models.review_log import ReviewLog
from app.models.user import User, UserProgress
from app.models.word import Word
from app.routers.auth import create_token, get_current_user
from app.routers import daily, quiz, review


class ReviewQuizApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app.config import get_settings
        cls.engine = create_engine(get_settings().DATABASE_URL)
        cls.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine)
        Base.metadata.create_all(bind=cls.engine)

        app = FastAPI()
        app.include_router(daily.router, prefix="/api/v1/daily", tags=["daily"])
        app.include_router(review.router, prefix="/api/v1/review", tags=["review"])
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

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=cls.engine)

    def setUp(self):
        Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self._seed_data()

    def _seed_data(self):
        db = self.SessionLocal()
        now = datetime.now(timezone.utc)

        user = User(
            openid="test-user",
            study_streak=0,
            total_study_days=0,
            last_study_date=None,
        )
        db.add(user)

        content1 = DailyContent(
            id=1,
            date=date.today(),
            theme_zh="咖啡文化",
            theme_en="Coffee Culture",
            category="life",
            category_zh="生活场景",
        )
        content2 = DailyContent(
            id=2,
            date=date.today() - timedelta(days=1),
            theme_zh="露营徒步",
            theme_en="Camping",
            category="travel",
            category_zh="旅行出行",
        )
        db.add_all([content1, content2])
        db.flush()

        phrase1 = Phrase(
            id=1,
            content_id=content1.id,
            phrase="on me",
            meaning="我请客",
            explanation="表示由我来买单。",
            example_1="This coffee is on me.",
            example_1_cn="这杯咖啡我请。",
            source="Friends",
        )
        phrase2 = Phrase(
            id=2,
            content_id=content2.id,
            phrase="pitch a tent",
            meaning="搭帐篷",
            explanation="在户外搭起帐篷。",
            example_1="Let's pitch a tent by the lake.",
            example_1_cn="我们在湖边搭帐篷吧。",
            source="Camping Guide",
        )
        phrase3 = Phrase(
            id=3,
            content_id=content1.id,
            phrase="grab a bite",
            meaning="吃点东西",
            explanation="快速吃一点东西。",
            example_1="Let's grab a bite after work.",
            example_1_cn="下班后去吃点东西吧。",
        )
        phrase4 = Phrase(
            id=4,
            content_id=content1.id,
            phrase="call it a day",
            meaning="今天就到这",
            explanation="表示今天的工作或活动到此结束。",
            example_1="Let's call it a day and head home.",
            example_1_cn="今天就到这儿吧，我们回家。",
        )
        phrase5 = Phrase(
            id=5,
            content_id=content1.id,
            phrase="hit the road",
            meaning="出发上路",
            explanation="表示开始旅行或离开。",
            example_1="We should hit the road before sunrise.",
            example_1_cn="我们得在日出前出发。",
        )
        phrase6 = Phrase(
            id=6,
            content_id=content1.id,
            phrase="piece of cake",
            meaning=None,
            explanation="表示某件事情非常容易，轻而易举。",
            example_1="The test was a piece of cake.",
            example_1_cn="这场考试非常容易。",
        )
        word1 = Word(
            id=1,
            content_id=content1.id,
            word="espresso",
            phonetic="/eˈspresəʊ/",
            part_of_speech="n.",
            meaning="浓缩咖啡",
            example="I ordered a double espresso.",
        )
        word2 = Word(
            id=2,
            content_id=content1.id,
            word="latte",
            phonetic="/ˈlɑːteɪ/",
            part_of_speech="n.",
            meaning="拿铁",
            example="She prefers a hot latte.",
        )
        word3 = Word(
            id=3,
            content_id=content1.id,
            word="mocha",
            phonetic="/ˈmɒkə/",
            part_of_speech="n.",
            meaning="摩卡",
            example="A mocha is sweeter than an americano.",
        )
        word4 = Word(
            id=4,
            content_id=content1.id,
            word="cappuccino",
            phonetic="/ˌkæpʊˈtʃiːnəʊ/",
            part_of_speech="n.",
            meaning="卡布奇诺",
            example="He ordered a cappuccino with oat milk.",
        )
        db.add_all([phrase1, phrase2, phrase3, phrase4, phrase5, phrase6, word1, word2, word3, word4])

        db.add_all([
            UserProgress(
                openid=user.openid,
                phrase_id=phrase1.id,
                mastery=1,
                review_count=1,
                last_review=now - timedelta(days=2),
                next_review=now - timedelta(hours=1),
            ),
            UserProgress(
                openid=user.openid,
                word_id=word1.id,
                mastery=2,
                review_count=1,
                last_review=now,
                next_review=now - timedelta(minutes=30),
            ),
            UserProgress(
                openid=user.openid,
                phrase_id=phrase2.id,
                mastery=4,
                review_count=3,
                last_review=now - timedelta(days=1),
                next_review=now + timedelta(days=10),
            ),
        ])

        db.commit()
        db.close()

    def test_review_overview_and_due_flow(self):
        today = date.today()
        overview = self.client.get(f"/api/v1/review/overview?year={today.year}&month={today.month}")
        self.assertEqual(overview.status_code, 200)
        overview_data = overview.json()
        self.assertEqual(overview_data["due_count"], 2)
        self.assertTrue(
            any(item["date"] == today.isoformat() for item in overview_data["calendar_dates"])
        )
        self.assertGreaterEqual(overview_data["memory_summary"]["new_count"], 1)
        self.assertEqual(overview_data["memory_summary"]["forgetting_count"], 2)
        self.assertEqual(overview_data["memory_summary"]["consolidating_count"], 0)
        self.assertEqual(overview_data["memory_summary"]["mastered_count"], 1)

        due = self.client.get("/api/v1/review/due")
        self.assertEqual(due.status_code, 200)
        due_data = due.json()
        self.assertEqual(due_data["total"], 2)
        self.assertEqual(due_data["items"][0]["item_type"], "phrase")

        complete = self.client.post("/api/v1/review/complete", json={
            "item_id": 1,
            "item_type": "phrase",
            "mastery": 4,
        })
        self.assertEqual(complete.status_code, 200)
        complete_data = complete.json()
        self.assertEqual(complete_data["updated"], 1)
        self.assertEqual(complete_data["study_streak"], 1)
        self.assertIsNotNone(complete_data["next_review_at"])

        db = self.SessionLocal()
        try:
            logs = db.query(ReviewLog).filter(
                ReviewLog.openid == "test-user",
                ReviewLog.item_type == "phrase",
                ReviewLog.item_id == 1,
            ).all()
            self.assertEqual(len(logs), 1)
            self.assertEqual(logs[0].mastery, 4)
        finally:
            db.close()

    def test_review_overview_uses_persistent_review_logs(self):
        today = date.today()
        first_review_at = datetime.combine(today - timedelta(days=2), datetime.min.time(), tzinfo=timezone.utc)
        second_review_at = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)

        db = self.SessionLocal()
        try:
            db.add_all([
                ReviewLog(
                    openid="test-user",
                    item_type="phrase",
                    item_id=1,
                    mastery=1,
                    reviewed_at=first_review_at,
                ),
                ReviewLog(
                    openid="test-user",
                    item_type="phrase",
                    item_id=1,
                    mastery=4,
                    reviewed_at=second_review_at,
                ),
                ReviewLog(
                    openid="test-user",
                    item_type="word",
                    item_id=1,
                    mastery=3,
                    reviewed_at=second_review_at + timedelta(hours=1),
                ),
            ])
            db.commit()
        finally:
            db.close()

        overview = self.client.get(f"/api/v1/review/overview?year={today.year}&month={today.month}")
        self.assertEqual(overview.status_code, 200)
        calendar = {item["date"]: item for item in overview.json()["calendar_dates"]}

        earlier = calendar[(today - timedelta(days=2)).isoformat()]
        current = calendar[today.isoformat()]
        self.assertEqual(earlier["reviewed_count"], 1)
        self.assertEqual(earlier["review_phrase_count"], 1)
        self.assertEqual(earlier["review_word_count"], 0)
        self.assertEqual(earlier["fuzzy_count"], 1)
        self.assertEqual(current["reviewed_count"], 2)
        self.assertEqual(current["review_phrase_count"], 1)
        self.assertEqual(current["review_word_count"], 1)
        self.assertEqual(current["remembered_count"], 1)
        self.assertEqual(current["solid_count"], 1)
        self.assertEqual(current["avg_mastery"], 3.5)

    def test_daily_today_returns_authenticated_progress(self):
        today = date.today()
        response = self.client.get(
            f"/api/v1/daily/today?target_date={today.isoformat()}",
            headers={"Authorization": "Bearer " + create_token("test-user")},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["progress"]["phrases_total"], 5)
        self.assertEqual(data["progress"]["words_total"], 4)
        self.assertEqual(data["progress"]["phrases_learned"], 1)
        self.assertEqual(data["progress"]["words_learned"], 1)
        self.assertEqual(data["review"]["due_count"], 2)

    def test_quiz_generation_modes_and_wrong_review_lifecycle(self):
        themes = self.client.get("/api/v1/quiz/themes")
        self.assertEqual(themes.status_code, 200)
        self.assertGreaterEqual(len(themes.json()), 2)

        generated = self.client.post("/api/v1/quiz/generate", json={
            "mode": "theme",
            "question_count": 10,
            "content_ids": [1],
            "question_types": ["phrase_meaning_choice", "word_phonetic_choice", "phrase_fill_input"],
        })
        self.assertEqual(generated.status_code, 200)
        questions = generated.json()
        question_types = {item["question_type"] for item in questions}
        self.assertIn("phrase_fill_input", question_types)
        self.assertIn("word_phonetic_choice", question_types)
        for question in questions:
            if question["question_type"] == "phrase_meaning_choice":
                for option in question["options"]:
                    self.assertNotIn("表示", option["text"])
                    self.assertLessEqual(len(option["text"]), 16)

        phrase_ids = [item["question_id"] for item in questions if item["question_type"] == "phrase_meaning_choice"]
        self.assertNotIn(6, phrase_ids)

        wrong_submit = self.client.post("/api/v1/quiz/submit", json={
            "answers": [{
                "question_id": 1,
                "question_type": "phrase_meaning_choice",
                "answer": "错误答案",
            }]
        })
        self.assertEqual(wrong_submit.status_code, 200)
        self.assertFalse(wrong_submit.json()["details"][0]["correct"])

        stats_after_wrong = self.client.get("/api/v1/quiz/stats")
        self.assertEqual(stats_after_wrong.status_code, 200)
        stats_wrong_data = stats_after_wrong.json()
        self.assertEqual(stats_wrong_data["wrong_count"], 1)
        self.assertTrue(any(item["question_type"] == "phrase_meaning_choice" for item in stats_wrong_data["by_type"]))

        wrong_review = self.client.post("/api/v1/quiz/generate", json={
            "mode": "wrong_review",
            "question_count": 5,
            "question_types": ["phrase_meaning_choice"],
        })
        self.assertEqual(wrong_review.status_code, 200)
        self.assertEqual(len(wrong_review.json()), 1)
        self.assertEqual(wrong_review.json()[0]["question_id"], 1)

        correct_submit = self.client.post("/api/v1/quiz/submit", json={
            "answers": [{
                "question_id": 1,
                "question_type": "phrase_meaning_choice",
                "answer": "我请客",
            }]
        })
        self.assertEqual(correct_submit.status_code, 200)
        self.assertTrue(correct_submit.json()["details"][0]["correct"])

        stats_after_fix = self.client.get("/api/v1/quiz/stats")
        self.assertEqual(stats_after_fix.status_code, 200)
        self.assertEqual(stats_after_fix.json()["wrong_count"], 0)


if __name__ == "__main__":
    unittest.main()
