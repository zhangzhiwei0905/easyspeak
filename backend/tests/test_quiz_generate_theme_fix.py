"""Fix checking unit tests for theme quiz multi-category select fix.

Validates: Requirements 2.1, 2.2, 3.1, 3.2, 3.3, 3.4

These tests lock down the exact detail literals and status codes returned by
the fixed `generate_quiz` endpoint. They serve as a regression safety net to
ensure the new three-segment semantic validation is never accidentally reverted.

Test strategy:
- Use FastAPI TestClient + in-memory SQLite with StaticPool.
- Authenticate via `create_token` (dev-mode compatible) + seeded User row.
- Strict assertions on `detail` string literals (not just substring checks).
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
from app.routers import quiz as quiz_router
from app.routers.auth import create_token

TEST_OPENID = "test-user-fix-checking"


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
        # Rich content for "work" category
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
        # Empty category: has daily_content but NO phrases/words
        content_empty = DailyContent(
            id=4,
            date=base_day - timedelta(days=3),
            theme_zh="空主题",
            theme_en="Empty Theme",
            category="empty_theme",
            category_zh="空主题",
        )

        db.add_all([content_travel, content_work, content_life, content_empty])
        db.flush()

        # Seed enough phrases and words for happy-path categories.
        # Need at least 4 phrases per content for distractor pool (3 distractors + 1 correct).
        phrases = [
            Phrase(id=1, content_id=1, phrase="hit the road", meaning="出发上路",
                   explanation="开始旅程", example_1="Time to hit the road.", example_1_cn="该出发了。"),
            Phrase(id=2, content_id=1, phrase="travel light", meaning="轻装出行",
                   explanation="少带行李", example_1="I always travel light.", example_1_cn="我总是轻装出行。"),
            Phrase(id=3, content_id=1, phrase="off the beaten path", meaning="人迹罕至的地方",
                   explanation="不走寻常路", example_1="We went off the beaten path.", example_1_cn="我们去了人迹罕至的地方。"),
            Phrase(id=4, content_id=1, phrase="catch a flight", meaning="赶飞机",
                   explanation="赶上航班", example_1="I need to catch a flight.", example_1_cn="我需要赶飞机。"),
            Phrase(id=5, content_id=2, phrase="call it a day", meaning="今天就到这",
                   explanation="结束当天工作", example_1="Let's call it a day.", example_1_cn="今天就到这吧。"),
            Phrase(id=6, content_id=2, phrase="get the ball rolling", meaning="开始行动",
                   explanation="启动某事", example_1="Let's get the ball rolling.", example_1_cn="让我们开始行动吧。"),
            Phrase(id=7, content_id=2, phrase="think outside the box", meaning="跳出框架思考",
                   explanation="创新思维", example_1="We need to think outside the box.", example_1_cn="我们需要跳出框架思考。"),
            Phrase(id=8, content_id=2, phrase="on the same page", meaning="达成共识",
                   explanation="意见一致", example_1="Are we on the same page?", example_1_cn="我们达成共识了吗？"),
            Phrase(id=9, content_id=3, phrase="grab a bite", meaning="吃点东西",
                   explanation="随便吃点东西", example_1="Let's grab a bite.", example_1_cn="我们去吃点东西吧。"),
            Phrase(id=10, content_id=3, phrase="sleep on it", meaning="考虑一晚再决定",
                   explanation="不急着做决定", example_1="Let me sleep on it.", example_1_cn="让我考虑一晚再说。"),
            Phrase(id=11, content_id=3, phrase="break the ice", meaning="打破僵局",
                   explanation="缓解尴尬气氛", example_1="He told a joke to break the ice.", example_1_cn="他讲了个笑话来打破僵局。"),
            Phrase(id=12, content_id=3, phrase="under the weather", meaning="身体不舒服",
                   explanation="感觉不太好", example_1="I'm feeling under the weather.", example_1_cn="我感觉身体不太舒服。"),
        ]
        db.add_all(phrases)

        words = [
            Word(id=1, content_id=1, word="itinerary", phonetic="/aɪˈtɪnəreri/", meaning="行程安排", example="Check the itinerary."),
            Word(id=2, content_id=1, word="destination", phonetic="/ˌdestɪˈneɪʃn/", meaning="目的地", example="What's your destination?"),
            Word(id=3, content_id=1, word="luggage", phonetic="/ˈlʌɡɪdʒ/", meaning="行李", example="Don't forget your luggage."),
            Word(id=4, content_id=1, word="passport", phonetic="/ˈpɑːspɔːrt/", meaning="护照", example="Show me your passport."),
            Word(id=5, content_id=2, word="agenda", phonetic="/əˈdʒendə/", meaning="议程", example="Check the agenda."),
            Word(id=6, content_id=2, word="deadline", phonetic="/ˈdedlaɪn/", meaning="截止日期", example="The deadline is tomorrow."),
            Word(id=7, content_id=2, word="colleague", phonetic="/ˈkɒliːɡ/", meaning="同事", example="Ask your colleague."),
            Word(id=8, content_id=2, word="presentation", phonetic="/ˌpreznˈteɪʃn/", meaning="演示", example="Prepare the presentation."),
            Word(id=9, content_id=3, word="espresso", phonetic="/eˈspresəʊ/", meaning="浓缩咖啡", example="A double espresso please."),
            Word(id=10, content_id=3, word="grocery", phonetic="/ˈɡroʊsəri/", meaning="杂货", example="I need to buy groceries."),
            Word(id=11, content_id=3, word="recipe", phonetic="/ˈresəpi/", meaning="食谱", example="Follow the recipe."),
            Word(id=12, content_id=3, word="apartment", phonetic="/əˈpɑːrtmənt/", meaning="公寓", example="A nice apartment."),
        ]
        db.add_all(words)
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    return app, client, engine


class ThemeQuizFixCheckingTest(unittest.TestCase):
    """Fix checking tests that lock down exact detail literals and status codes.

    Validates: Requirements 2.1, 2.2, 3.1, 3.2, 3.3, 3.4
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

    # --- Test Cases ---------------------------------------------------------

    def test_theme_missing_params_returns_422_with_missing_semantics(self):
        """Theme mode with no category and no content_ids → 422 with exact detail.

        Validates: Requirements 3.1
        """
        response = self._post_generate({"mode": "theme"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["detail"],
            "请选择至少一个类别后再开始主题测验",
        )

    def test_theme_category_not_matching_returns_422_with_empty_content_semantics(self):
        """Theme mode with category that has no matching daily_content → 422.

        Validates: Requirements 2.1
        """
        response = self._post_generate({
            "mode": "theme",
            "category": ["nonexistent"],
        })
        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["detail"],
            "所选类别暂无可用题目，请更换类别后重试",
        )

    def test_theme_category_matched_but_no_phrase_word_returns_422_with_empty_content_semantics(self):
        """Theme mode with category matching daily_content but no phrases/words → 422.

        Validates: Requirements 2.2
        """
        response = self._post_generate({
            "mode": "theme",
            "category": ["empty_theme"],
        })
        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["detail"],
            "所选类别暂无可用题目，请更换类别后重试",
        )

    def test_theme_happy_path_returns_questions(self):
        """Theme mode with valid category and sufficient data → 200 + questions.

        Validates: Requirements 3.2
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

    def test_random_mode_still_works_without_category(self):
        """Random mode without category → 200.

        Validates: Requirements 3.3
        """
        response = self._post_generate({
            "mode": "random",
            "question_count": 3,
        })
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIsInstance(body, list)

    def test_wrong_review_mode_still_works(self):
        """Wrong review mode → 200 (with questions) or 404 (empty pool).

        When the wrong-answer pool is empty, the current implementation returns
        an empty list (HTTP 200) or 404 + "没有可用的题目". Both are acceptable.

        Validates: Requirements 3.4
        """
        response = self._post_generate({
            "mode": "wrong_review",
            "question_count": 3,
        })
        self.assertIn(
            response.status_code,
            {200, 404},
            f"wrong_review should return 200 or 404, got {response.status_code}",
        )
        if response.status_code == 404:
            self.assertEqual(response.json()["detail"], "没有可用的题目")

    def test_source_code_does_not_contain_legacy_literal(self):
        """Regression guard: the legacy misleading detail string must not exist in source.

        Validates: Requirements 2.1, 2.2
        """
        quiz_router_path = Path(__file__).resolve().parents[1] / "app" / "routers" / "quiz.py"
        source = quiz_router_path.read_text(encoding="utf-8")
        self.assertNotIn(
            "theme mode requires content_ids or category",
            source,
            "Legacy detail literal still present in quiz.py — fix may have been reverted!",
        )


if __name__ == "__main__":
    unittest.main()

    def test_get_categories_groups_content_by_category_key(self):
        response = self.client.get("/api/v1/quiz/categories")

        assert response.status_code == 200
        categories = response.json()
        by_key = {item["key"]: item for item in categories}

        assert set(by_key) >= {"travel", "work", "life"}
        assert by_key["travel"]["label"] == "旅行出行"
        assert by_key["travel"]["content_count"] == 1
        assert by_key["travel"]["question_count"] > 0

    def test_theme_generate_accepts_category_keys(self):
        response = self.client.post(
            "/api/v1/quiz/generate",
            headers=self.auth_headers,
            json={"mode": "theme", "question_count": 5, "category": ["travel", "work"]},
        )

        assert response.status_code == 200
        questions = response.json()
        assert len(questions) > 0

    def test_theme_generate_accepts_category_labels_and_comma_string(self):
        by_label = self.client.post(
            "/api/v1/quiz/generate",
            headers=self.auth_headers,
            json={"mode": "theme", "question_count": 5, "category": ["旅行出行"]},
        )
        by_comma = self.client.post(
            "/api/v1/quiz/generate",
            headers=self.auth_headers,
            json={"mode": "theme", "question_count": 5, "category": ["travel,work"]},
        )
        by_encoded_comma = self.client.post(
            "/api/v1/quiz/generate",
            headers=self.auth_headers,
            json={"mode": "theme", "question_count": 5, "category": ["travel%2Cwork"]},
        )

        assert by_label.status_code == 200
        assert len(by_label.json()) > 0
        assert by_comma.status_code == 200
        assert len(by_comma.json()) > 0
        assert by_encoded_comma.status_code == 200
        assert len(by_encoded_comma.json()) > 0
