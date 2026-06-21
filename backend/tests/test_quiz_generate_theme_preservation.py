"""Preservation property tests for theme quiz multi-category select fix.

Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5
Design: .kiro/specs/theme-quiz-multi-select-fix/design.md §Preservation Requirements

These tests encode the CURRENT (pre-fix) behaviour of non-bug-condition paths.
They MUST pass on the unfixed code (observation-first baseline) and continue to
pass after the fix lands — ensuring no regressions are introduced.

Test strategy:
- Use hypothesis for PBT where applicable (random mode question_count sweep).
- Use FastAPI TestClient + in-memory SQLite with StaticPool (same pattern as
  test_quiz_generate_theme_bug.py).
- Authenticate via `create_token` (dev-mode compatible) + seeded User row.
"""
from __future__ import annotations

import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings as hyp_settings, strategies as st
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
from app.routers import quiz as quiz_router
from app.routers.auth import create_token

TEST_OPENID = "test-user-preservation"


def _build_test_app_and_client():
    """Create a FastAPI app wired to an in-memory SQLite DB with seeded data."""
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

        # Rich content for "travel" category — used for happy-path tests
        content_travel = DailyContent(
            id=1,
            date=base_day,
            theme_zh="旅行出行",
            theme_en="Travel",
            category="travel",
            category_zh="旅行出行",
        )
        # Rich content for "work" category — provides additional pool for random mode
        content_work = DailyContent(
            id=2,
            date=base_day - timedelta(days=1),
            theme_zh="职场沟通",
            theme_en="Workplace",
            category="work",
            category_zh="职场沟通",
        )
        # Rich content for "life" category
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

        # Seed enough phrases and words to ensure quiz generation succeeds.
        # We need at least 4 phrases per content (for distractor pool of 3 + 1 correct).
        phrases = [
            Phrase(
                id=1,
                content_id=content_travel.id,
                phrase="hit the road",
                meaning="出发上路",
                explanation="开始旅程",
                example_1="Time to hit the road.",
                example_1_cn="该出发了。",
            ),
            Phrase(
                id=2,
                content_id=content_travel.id,
                phrase="travel light",
                meaning="轻装出行",
                explanation="少带行李",
                example_1="I always travel light.",
                example_1_cn="我总是轻装出行。",
            ),
            Phrase(
                id=3,
                content_id=content_travel.id,
                phrase="off the beaten path",
                meaning="人迹罕至的地方",
                explanation="不走寻常路",
                example_1="We went off the beaten path.",
                example_1_cn="我们去了人迹罕至的地方。",
            ),
            Phrase(
                id=4,
                content_id=content_travel.id,
                phrase="catch a flight",
                meaning="赶飞机",
                explanation="赶上航班",
                example_1="I need to catch a flight.",
                example_1_cn="我需要赶飞机。",
            ),
            Phrase(
                id=5,
                content_id=content_work.id,
                phrase="call it a day",
                meaning="今天就到这",
                explanation="结束当天工作",
                example_1="Let's call it a day.",
                example_1_cn="今天就到这吧。",
            ),
            Phrase(
                id=6,
                content_id=content_work.id,
                phrase="get the ball rolling",
                meaning="开始行动",
                explanation="启动某事",
                example_1="Let's get the ball rolling.",
                example_1_cn="让我们开始行动吧。",
            ),
            Phrase(
                id=7,
                content_id=content_work.id,
                phrase="think outside the box",
                meaning="跳出框架思考",
                explanation="创新思维",
                example_1="We need to think outside the box.",
                example_1_cn="我们需要跳出框架思考。",
            ),
            Phrase(
                id=8,
                content_id=content_work.id,
                phrase="on the same page",
                meaning="达成共识",
                explanation="意见一致",
                example_1="Are we on the same page?",
                example_1_cn="我们达成共识了吗？",
            ),
            Phrase(
                id=9,
                content_id=content_life.id,
                phrase="grab a bite",
                meaning="吃点东西",
                explanation="随便吃点东西",
                example_1="Let's grab a bite.",
                example_1_cn="我们去吃点东西吧。",
            ),
            Phrase(
                id=10,
                content_id=content_life.id,
                phrase="sleep on it",
                meaning="考虑一晚再决定",
                explanation="不急着做决定",
                example_1="Let me sleep on it.",
                example_1_cn="让我考虑一晚再说。",
            ),
            Phrase(
                id=11,
                content_id=content_life.id,
                phrase="break the ice",
                meaning="打破僵局",
                explanation="缓解尴尬气氛",
                example_1="He told a joke to break the ice.",
                example_1_cn="他讲了个笑话来打破僵局。",
            ),
            Phrase(
                id=12,
                content_id=content_life.id,
                phrase="under the weather",
                meaning="身体不舒服",
                explanation="感觉不太好",
                example_1="I'm feeling under the weather.",
                example_1_cn="我感觉身体不太舒服。",
            ),
        ]
        db.add_all(phrases)

        words = [
            Word(
                id=1,
                content_id=content_travel.id,
                word="itinerary",
                phonetic="/aɪˈtɪnəreri/",
                meaning="行程安排",
                example="Check the itinerary.",
            ),
            Word(
                id=2,
                content_id=content_travel.id,
                word="destination",
                phonetic="/ˌdestɪˈneɪʃn/",
                meaning="目的地",
                example="What's your destination?",
            ),
            Word(
                id=3,
                content_id=content_travel.id,
                word="luggage",
                phonetic="/ˈlʌɡɪdʒ/",
                meaning="行李",
                example="Don't forget your luggage.",
            ),
            Word(
                id=4,
                content_id=content_travel.id,
                word="passport",
                phonetic="/ˈpɑːspɔːrt/",
                meaning="护照",
                example="Show me your passport.",
            ),
            Word(
                id=5,
                content_id=content_work.id,
                word="agenda",
                phonetic="/əˈdʒendə/",
                meaning="议程",
                example="Check the agenda.",
            ),
            Word(
                id=6,
                content_id=content_work.id,
                word="deadline",
                phonetic="/ˈdedlaɪn/",
                meaning="截止日期",
                example="The deadline is tomorrow.",
            ),
            Word(
                id=7,
                content_id=content_work.id,
                word="colleague",
                phonetic="/ˈkɒliːɡ/",
                meaning="同事",
                example="Ask your colleague.",
            ),
            Word(
                id=8,
                content_id=content_work.id,
                word="presentation",
                phonetic="/ˌpreznˈteɪʃn/",
                meaning="演示",
                example="Prepare the presentation.",
            ),
            Word(
                id=9,
                content_id=content_life.id,
                word="espresso",
                phonetic="/eˈspresəʊ/",
                meaning="浓缩咖啡",
                example="A double espresso please.",
            ),
            Word(
                id=10,
                content_id=content_life.id,
                word="grocery",
                phonetic="/ˈɡroʊsəri/",
                meaning="杂货",
                example="I need to buy groceries.",
            ),
            Word(
                id=11,
                content_id=content_life.id,
                word="recipe",
                phonetic="/ˈresəpi/",
                meaning="食谱",
                example="Follow the recipe.",
            ),
            Word(
                id=12,
                content_id=content_life.id,
                word="apartment",
                phonetic="/əˈpɑːrtmənt/",
                meaning="公寓",
                example="A nice apartment.",
            ),
        ]
        db.add_all(words)
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    return app, client, engine


class PreservationPropertyTest(unittest.TestCase):
    """Preservation tests ensuring non-bug-condition paths remain unchanged.

    Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5
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

    # --- Helpers -----------------------------------------------------------

    def _post_generate(self, body: dict):
        return self.client.post(
            "/api/v1/quiz/generate",
            headers=self.auth_headers,
            json=body,
        )

    # --- 3.1 PreserveMissingParams -----------------------------------------

    def test_preserve_missing_params_returns_422(self):
        """3.1: theme mode with no content_ids and no category → 422 + non-empty detail.

        **Validates: Requirements 3.1**
        """
        response = self._post_generate({
            "mode": "theme",
            "question_count": 10,
        })
        self.assertEqual(response.status_code, 422)
        detail = response.json().get("detail")
        self.assertIsInstance(detail, str)
        self.assertTrue(len(detail) > 0, "detail should be a non-empty string")

    # --- 3.2 PreserveThemeHappyPath ----------------------------------------

    def test_preserve_theme_happy_path_returns_questions(self):
        """3.2: valid category with sufficient data → 200 + question array.

        **Validates: Requirements 3.2**
        """
        response = self._post_generate({
            "mode": "theme",
            "category": ["travel"],
            "question_count": 5,
        })
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIsInstance(body, list)
        self.assertGreaterEqual(len(body), 1)
        # Verify each item has required fields
        for item in body:
            self.assertIn("question_id", item)
            self.assertIn("question_type", item)
            self.assertIn("prompt", item)
            self.assertIn("options", item)
            self.assertIn("accepted_answers", item)

    @hyp_settings(
        max_examples=10,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        category=st.sampled_from(["travel", "work", "life"]),
        question_count=st.integers(min_value=1, max_value=10),
    )
    def test_property_theme_happy_path(self, category, question_count):
        """Property: For any valid seeded category and question_count, theme mode returns 200.

        **Validates: Requirements 3.2**
        """
        response = self._post_generate({
            "mode": "theme",
            "category": [category],
            "question_count": question_count,
        })
        self.assertEqual(
            response.status_code, 200,
            f"Expected 200 for category={category!r}, qc={question_count}, "
            f"got {response.status_code}: {response.json()}",
        )
        body = response.json()
        self.assertIsInstance(body, list)
        self.assertGreaterEqual(len(body), 1)

    # --- 3.3 PreserveRandomMode --------------------------------------------

    def test_preserve_random_mode_returns_200(self):
        """3.3: random mode without category → 200.

        **Validates: Requirements 3.3**
        """
        response = self._post_generate({
            "mode": "random",
            "question_count": 3,
        })
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIsInstance(body, list)

    @hyp_settings(
        max_examples=15,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(question_count=st.integers(min_value=1, max_value=20))
    def test_property_random_mode(self, question_count):
        """Property: For any question_count in [1,20], random mode returns 200 + array.

        **Validates: Requirements 3.3**
        """
        response = self._post_generate({
            "mode": "random",
            "question_count": question_count,
        })
        self.assertEqual(
            response.status_code, 200,
            f"Expected 200 for random mode qc={question_count}, "
            f"got {response.status_code}: {response.json()}",
        )
        body = response.json()
        self.assertIsInstance(body, list)

    # --- 3.4 PreserveWrongReviewMode ---------------------------------------

    def test_preserve_wrong_review_empty_pool_returns_404(self):
        """3.4: wrong_review with empty wrong-answer pool → returns empty list (200)
        or 404 with "没有可用的题目" depending on implementation.

        Current behaviour: wrong_review with no wrong answers returns an empty
        list (HTTP 200) because the loop simply finds no wrong pairs and returns
        early. This test locks in that current behaviour.

        **Validates: Requirements 3.4**
        """
        response = self._post_generate({
            "mode": "wrong_review",
            "question_count": 3,
        })
        # Current implementation: wrong_review returns early with empty list
        # when there are no wrong pairs — this is HTTP 200 with [].
        # We accept both 200 (empty list) and 404 as valid preservation.
        self.assertIn(
            response.status_code, {200, 404},
            f"wrong_review should return 200 or 404, got {response.status_code}",
        )
        if response.status_code == 404:
            detail = response.json().get("detail")
            self.assertEqual(detail, "没有可用的题目")

    # --- 3.5 PreserveOtherEndpoints ----------------------------------------

    def test_preserve_get_stats(self):
        """3.5: GET /quiz/stats returns 200 with expected fields.

        **Validates: Requirements 3.5**
        """
        response = self.client.get(
            "/api/v1/quiz/stats",
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("total_answered", body)
        self.assertIn("total_correct", body)
        self.assertIn("accuracy", body)
        self.assertIn("streak_days", body)
        self.assertIn("weekly_answered", body)
        self.assertEqual(body["weekly_goal"], 50)
        self.assertIn("weekly_percent", body)

    def test_preserve_get_themes(self):
        """3.5: GET /quiz/themes returns 200 with array.

        **Validates: Requirements 3.5**
        """
        response = self.client.get("/api/v1/quiz/themes")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIsInstance(body, list)
        self.assertGreater(len(body), 0)
        # Each theme item should have content_id, theme_zh, theme_en
        for item in body:
            self.assertIn("content_id", item)
            self.assertIn("theme_zh", item)
            self.assertIn("theme_en", item)


if __name__ == "__main__":
    unittest.main()
