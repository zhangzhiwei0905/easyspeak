"""Cross-endpoint regression smoke tests.

Validates: Requirements 3.5
Design: .kiro/specs/theme-quiz-multi-select-fix/design.md §Preservation Requirements

These smoke tests verify that non-generate_quiz endpoints remain unaffected by
the theme quiz multi-category select fix. They cover:
- POST /quiz/submit
- GET /quiz/stats
- GET /quiz/themes
- POST /learn/session
- POST /learn/progress
- POST /learn/report

Test strategy:
- Use FastAPI TestClient + in-memory SQLite with StaticPool (same pattern as
  other tests in this spec).
- Authenticate via `create_token` (dev-mode compatible) + seeded User row.
- Include all relevant routers: auth, quiz, learn.
"""
from __future__ import annotations

import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.models  # noqa: F401  — registers mappers
from app.database import Base, get_db
from app.models.daily import DailyContent
from app.models.phrase import Phrase
from app.models.user import User
from app.models.word import Word
from app.routers import auth as auth_router
from app.routers import learn as learn_router
from app.routers import quiz as quiz_router
from app.routers.auth import create_token

TEST_OPENID = "test-user-cross-endpoint"


def _build_test_app_and_client():
    """Create a FastAPI app wired to an in-memory SQLite DB with seeded data.

    Seeds enough data for all smoke tests:
    - User for auth
    - DailyContent with category "travel" (content_id=1) with 4+ phrases and 4+ words
      (needed for quiz generation and learn session distractor pool)
    - Additional DailyContent entries to provide a richer distractor pool for learn
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    app = FastAPI()
    app.include_router(auth_router.router, prefix="/api/v1/auth", tags=["auth"])
    app.include_router(quiz_router.router, prefix="/api/v1/quiz", tags=["quiz"])
    app.include_router(learn_router.router, prefix="/api/v1/learn", tags=["learn"])

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # Seed baseline data
    db = SessionLocal()
    try:
        user = User(openid=TEST_OPENID)
        db.add(user)

        base_day = date.today()

        # Content for "travel" category — primary test content
        content_travel = DailyContent(
            id=1,
            date=base_day,
            theme_zh="旅行出行",
            theme_en="Travel",
            category="travel",
            category_zh="旅行出行",
        )
        # Content for "work" category — provides additional distractor pool
        content_work = DailyContent(
            id=2,
            date=base_day - timedelta(days=1),
            theme_zh="职场沟通",
            theme_en="Workplace",
            category="work",
            category_zh="职场沟通",
        )
        # Content for "life" category — provides additional distractor pool
        content_life = DailyContent(
            id=3,
            date=base_day - timedelta(days=2),
            theme_zh="生活场景",
            theme_en="Daily Life",
            category="life",
            category_zh="生活场景",
        )

        db.add_all([content_travel, content_work, content_life])
        db.flush()

        # Seed phrases — at least 4 per content for distractor pool
        phrases = [
            Phrase(id=1, content_id=1, phrase="hit the road", meaning="出发上路",
                   explanation="开始旅程", example_1="Time to hit the road.",
                   example_1_cn="该出发了。"),
            Phrase(id=2, content_id=1, phrase="travel light", meaning="轻装出行",
                   explanation="少带行李", example_1="I always travel light.",
                   example_1_cn="我总是轻装出行。"),
            Phrase(id=3, content_id=1, phrase="off the beaten path", meaning="人迹罕至的地方",
                   explanation="不走寻常路", example_1="We went off the beaten path.",
                   example_1_cn="我们去了人迹罕至的地方。"),
            Phrase(id=4, content_id=1, phrase="catch a flight", meaning="赶飞机",
                   explanation="赶上航班", example_1="I need to catch a flight.",
                   example_1_cn="我需要赶飞机。"),
            Phrase(id=5, content_id=2, phrase="call it a day", meaning="今天就到这",
                   explanation="结束当天工作", example_1="Let's call it a day.",
                   example_1_cn="今天就到这吧。"),
            Phrase(id=6, content_id=2, phrase="get the ball rolling", meaning="开始行动",
                   explanation="启动某事", example_1="Let's get the ball rolling.",
                   example_1_cn="让我们开始行动吧。"),
            Phrase(id=7, content_id=2, phrase="think outside the box", meaning="跳出框架思考",
                   explanation="创新思维", example_1="We need to think outside the box.",
                   example_1_cn="我们需要跳出框架思考。"),
            Phrase(id=8, content_id=2, phrase="on the same page", meaning="达成共识",
                   explanation="意见一致", example_1="Are we on the same page?",
                   example_1_cn="我们达成共识了吗？"),
            Phrase(id=9, content_id=3, phrase="grab a bite", meaning="吃点东西",
                   explanation="随便吃点东西", example_1="Let's grab a bite.",
                   example_1_cn="我们去吃点东西吧。"),
            Phrase(id=10, content_id=3, phrase="sleep on it", meaning="考虑一晚再决定",
                   explanation="不急着做决定", example_1="Let me sleep on it.",
                   example_1_cn="让我考虑一晚再说。"),
            Phrase(id=11, content_id=3, phrase="break the ice", meaning="打破僵局",
                   explanation="缓解尴尬气氛", example_1="He told a joke to break the ice.",
                   example_1_cn="他讲了个笑话来打破僵局。"),
            Phrase(id=12, content_id=3, phrase="under the weather", meaning="身体不舒服",
                   explanation="感觉不太好", example_1="I'm feeling under the weather.",
                   example_1_cn="我感觉身体不太舒服。"),
        ]
        db.add_all(phrases)

        # Seed words — at least 4 per content for distractor pool
        words = [
            Word(id=1, content_id=1, word="itinerary", phonetic="/aɪˈtɪnəreri/",
                 meaning="行程安排", example="Check the itinerary."),
            Word(id=2, content_id=1, word="destination", phonetic="/ˌdestɪˈneɪʃn/",
                 meaning="目的地", example="What's your destination?"),
            Word(id=3, content_id=1, word="luggage", phonetic="/ˈlʌɡɪdʒ/",
                 meaning="行李", example="Don't forget your luggage."),
            Word(id=4, content_id=1, word="passport", phonetic="/ˈpɑːspɔːrt/",
                 meaning="护照", example="Show me your passport."),
            Word(id=5, content_id=2, word="agenda", phonetic="/əˈdʒendə/",
                 meaning="议程", example="Check the agenda."),
            Word(id=6, content_id=2, word="deadline", phonetic="/ˈdedlaɪn/",
                 meaning="截止日期", example="The deadline is tomorrow."),
            Word(id=7, content_id=2, word="colleague", phonetic="/ˈkɒliːɡ/",
                 meaning="同事", example="Ask your colleague."),
            Word(id=8, content_id=2, word="presentation", phonetic="/ˌpreznˈteɪʃn/",
                 meaning="演示", example="Prepare the presentation."),
            Word(id=9, content_id=3, word="espresso", phonetic="/eˈspresəʊ/",
                 meaning="浓缩咖啡", example="A double espresso please."),
            Word(id=10, content_id=3, word="grocery", phonetic="/ˈɡroʊsəri/",
                 meaning="杂货", example="I need to buy groceries."),
            Word(id=11, content_id=3, word="recipe", phonetic="/ˈresəpi/",
                 meaning="食谱", example="Follow the recipe."),
            Word(id=12, content_id=3, word="apartment", phonetic="/əˈpɑːrtmənt/",
                 meaning="公寓", example="A nice apartment."),
        ]
        db.add_all(words)
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    return app, client, engine


class CrossEndpointRegressionSmokeTest(unittest.TestCase):
    """Smoke tests for non-generate_quiz endpoints to ensure no regression.

    Validates: Requirements 3.5
    """

    @classmethod
    def setUpClass(cls):
        cls.app, cls.client, cls.engine = _build_test_app_and_client()
        cls.auth_headers = {
            "Authorization": f"Bearer {create_token(TEST_OPENID)}"
        }

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=cls.engine)

    # --- Quiz Endpoints ----------------------------------------------------

    def test_quiz_submit_returns_result(self):
        """POST /quiz/submit: submit a valid answer and get result.

        First generates a quiz to get a valid question_id and option,
        then submits an answer.

        Validates: Requirements 3.5
        """
        # Step 1: Generate a quiz to get a valid question
        gen_response = self.client.post(
            "/api/v1/quiz/generate",
            headers=self.auth_headers,
            json={
                "mode": "theme",
                "category": ["travel"],
                "question_count": 1,
            },
        )
        self.assertEqual(gen_response.status_code, 200)
        questions = gen_response.json()
        self.assertGreaterEqual(len(questions), 1)

        question = questions[0]
        question_id = question["question_id"]
        question_type = question["question_type"]
        # Pick the first option text as the answer (may or may not be correct)
        selected_answer = question["options"][0]["text"] if question["options"] else "test"

        # Step 2: Submit the answer
        submit_response = self.client.post(
            "/api/v1/quiz/submit",
            headers=self.auth_headers,
            json={
                "answers": [
                    {
                        "question_id": question_id,
                        "question_type": question_type,
                        "answer": selected_answer,
                    }
                ]
            },
        )
        self.assertIn(
            submit_response.status_code,
            {200, 201},
            f"Expected 200 or 201, got {submit_response.status_code}: {submit_response.text}",
        )
        body = submit_response.json()
        # QuizResult schema has total, correct, accuracy, details
        self.assertIn("total", body)
        self.assertIn("correct", body)
        self.assertIn("accuracy", body)
        self.assertIn("details", body)
        # Each detail item should have 'correct' field (is_correct equivalent)
        self.assertGreaterEqual(len(body["details"]), 1)
        self.assertIn("correct", body["details"][0])

    def test_quiz_stats_returns_200(self):
        """GET /quiz/stats: returns 200 with non-empty JSON object.

        Validates: Requirements 3.5
        """
        response = self.client.get(
            "/api/v1/quiz/stats",
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIsInstance(body, dict)
        # QuizStats schema fields
        self.assertIn("total_answered", body)
        self.assertIn("total_correct", body)
        self.assertIn("accuracy", body)

    def test_quiz_themes_returns_200_array(self):
        """GET /quiz/themes: returns 200 with array.

        Validates: Requirements 3.5
        """
        response = self.client.get("/api/v1/quiz/themes")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIsInstance(body, list)
        self.assertGreater(len(body), 0)
        # Each item should have content_id, theme_zh, theme_en
        for item in body:
            self.assertIn("content_id", item)
            self.assertIn("theme_zh", item)
            self.assertIn("theme_en", item)

    # --- Learn Endpoints ---------------------------------------------------

    def test_learn_session_returns_quizzes(self):
        """POST /learn/session: create a phrase learning session.

        Uses content_id=1 (travel) which has 4 phrases — enough for
        distractor pool.

        Validates: Requirements 3.5
        """
        response = self.client.post(
            "/api/v1/learn/session",
            headers=self.auth_headers,
            json={
                "content_id": 1,
                "learn_type": "phrase",
            },
        )
        self.assertEqual(
            response.status_code, 200,
            f"Expected 200, got {response.status_code}: {response.text}",
        )
        body = response.json()
        self.assertIn("session_id", body)
        self.assertIn("items", body)
        self.assertGreaterEqual(len(body["items"]), 1)
        # Each phrase item should have stage2_quiz and stage3_quiz
        first_item = body["items"][0]
        self.assertIn("stage2_quiz", first_item)
        self.assertIn("stage3_quiz", first_item)

    def test_learn_progress_accepts_update(self):
        """POST /learn/progress: submit mastery progress update.

        Validates: Requirements 3.5
        """
        response = self.client.post(
            "/api/v1/learn/progress",
            headers=self.auth_headers,
            json={
                "content_id": 1,
                "learn_type": "phrase",
                "items": [
                    {
                        "item_id": 1,
                        "item_type": "phrase",
                        "mastery": 3,
                    }
                ],
            },
        )
        self.assertIn(
            response.status_code,
            {200, 204},
            f"Expected 200 or 204, got {response.status_code}: {response.text}",
        )

    def test_learn_report_accepts_submission(self):
        """POST /learn/report: submit learning completion report.

        Validates: Requirements 3.5
        """
        response = self.client.post(
            "/api/v1/learn/report",
            headers=self.auth_headers,
            json={
                "content_id": 1,
                "learn_type": "phrase",
                "total_items": 4,
                "first_pass_correct": 3,
                "retry_correct": 1,
                "duration_seconds": 120,
                "mastery_distribution": {
                    "forgot": 0,
                    "fuzzy": 1,
                    "remembered": 2,
                    "solid": 1,
                },
            },
        )
        self.assertIn(
            response.status_code,
            {200, 204},
            f"Expected 200 or 204, got {response.status_code}: {response.text}",
        )
        if response.status_code == 200:
            body = response.json()
            # LearnReportResponse has study_streak, total_study_days, message
            self.assertIn("study_streak", body)
            self.assertIn("total_study_days", body)


if __name__ == "__main__":
    unittest.main()
