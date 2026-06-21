"""Bug condition exploration property test for theme quiz multi-category select.

Validates: Requirements 1.1, 1.2, 2.1, 2.2
Design: .kiro/specs/theme-quiz-multi-select-fix/design.md §Bug Condition (C1, C2)

This test is EXPECTED TO FAIL on the unfixed code in `backend/app/routers/quiz.py::generate_quiz`.
Failure confirms the bug is reproducible. After the fix in Task 3 lands, the same test SHALL
transition to PASS because it encodes the post-fix `expectedBehavior` (HTTP 4xx + non-misleading
`detail` with "类别" / category-empty Chinese semantics).

Test strategy (scoped PBT):
- Use hypothesis to sweep the sub-branches identified in design.md §Bug Condition:
  * C1: `category` non-empty but no matching `daily_content.category`
  * C2: `category` matches `daily_content` but the content has no phrases/words to build a quiz
- Use FastAPI TestClient + in-memory SQLite with StaticPool so the whole suite is hermetic.
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
from app.routers.auth import create_token, get_current_user

# Categories actually present in the seeded test DB. Anything NOT in this set
# represents the C1 bug branch (category value with no daily_content match).
SEEDED_CATEGORIES_WITH_POOL = ("work", "life", "travel")
# A category that exists in daily_content but whose content has NO phrases/words → C2
SEEDED_EMPTY_CATEGORY = "empty_theme"

TEST_OPENID = "test-user-theme-bug"
BUG_DETAIL = "theme mode requires content_ids or category"
EMPTY_FALLBACK_DETAIL = "没有可用的题目"


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
    # Note: we intentionally DO NOT override get_current_user; we exercise
    # the real JWT decode path with a `create_token`-minted token so that
    # the integration test mirrors production auth behaviour.

    # Seed baseline data
    db = SessionLocal()
    try:
        user = User(openid=TEST_OPENID)
        db.add(user)

        base_day = date.today()

        # Two categories with rich content — used for happy-path comparison
        # and to ensure the "C1 no match" branch is truly isolated from
        # happy-path categories.
        content_work = DailyContent(
            id=1,
            date=base_day,
            theme_zh="职场沟通",
            theme_en="Workplace",
            category="work",
            category_zh="职场沟通",
        )
        content_life = DailyContent(
            id=2,
            date=base_day - timedelta(days=1),
            theme_zh="生活场景",
            theme_en="Daily Life",
            category="life",
            category_zh="生活场景",
        )
        content_travel = DailyContent(
            id=3,
            date=base_day - timedelta(days=2),
            theme_zh="旅行出行",
            theme_en="Travel",
            category="travel",
            category_zh="旅行出行",
        )
        # C2 branch: category matches but no phrases/words attached
        content_empty = DailyContent(
            id=4,
            date=base_day - timedelta(days=3),
            theme_zh="空主题",
            theme_en="Empty Theme",
            category=SEEDED_EMPTY_CATEGORY,
            category_zh="空主题",
        )

        db.add_all([content_work, content_life, content_travel, content_empty])
        db.flush()

        # Minimal phrase/word pool for happy-path categories so that theme
        # mode on "work"/"life"/"travel" would not itself fall into C2.
        db.add_all([
            Phrase(
                id=1,
                content_id=content_work.id,
                phrase="call it a day",
                meaning="今天就到这",
                explanation="结束当天工作",
                example_1="Let's call it a day.",
                example_1_cn="今天就到这吧。",
            ),
            Phrase(
                id=2,
                content_id=content_life.id,
                phrase="grab a bite",
                meaning="吃点东西",
                explanation="随便吃点东西",
                example_1="Let's grab a bite.",
                example_1_cn="我们去吃点东西吧。",
            ),
            Phrase(
                id=3,
                content_id=content_travel.id,
                phrase="hit the road",
                meaning="出发上路",
                explanation="开始旅程",
                example_1="Time to hit the road.",
                example_1_cn="该出发了。",
            ),
            Word(
                id=1,
                content_id=content_work.id,
                word="agenda",
                phonetic="/əˈdʒendə/",
                meaning="议程",
                example="Check the agenda.",
            ),
            Word(
                id=2,
                content_id=content_life.id,
                word="espresso",
                phonetic="/eˈspresəʊ/",
                meaning="浓缩咖啡",
                example="A double espresso please.",
            ),
        ])
        db.commit()
    finally:
        db.close()

    client = TestClient(app)
    return app, client, engine


class ThemeQuizBugConditionTest(unittest.TestCase):
    """Exploration test for C1 & C2 branches of the theme-quiz multi-select bug."""

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

    def _assert_bug_condition_response(self, response, case_label: str):
        """expectedBehavior(response) == False under the current (unfixed) impl.

        When Task 3's fix lands, this assertion SHALL continue to pass because
        it encodes `expectedBehavior(response) == True`:
          - status_code ∈ {422} (post-fix) or {404, 422} (pre-fix)
          - detail must NOT be the misleading legacy string
          - detail must be a non-empty string indicating "no available questions
            under the selected category" (Chinese)

        Pre-fix the first two clauses fail simultaneously (bug is reproduced).
        Post-fix all three hold.
        """
        self.assertIn(
            response.status_code,
            {404, 422},
            f"[{case_label}] status_code should be a 4xx error, got {response.status_code}",
        )
        detail = response.json().get("detail")
        self.assertIsInstance(detail, str, f"[{case_label}] missing detail string: {response.json()}")

        # Post-fix expected behaviour: detail does NOT equal the misleading legacy string
        # AND points at "所选类别暂无可用题目" semantics (contains 类别 AND not a
        # pure "请求参数缺失" message).
        self.assertNotEqual(
            detail,
            BUG_DETAIL,
            f"[{case_label}] detail still the misleading legacy string: {detail!r}",
        )
        self.assertNotEqual(
            detail,
            EMPTY_FALLBACK_DETAIL,
            f"[{case_label}] detail fell back to generic 404 text, users see "
            f"'请求的资源不存在' via api.js: {detail!r}",
        )
        # post-fix文案含"类别" / "题目"核心语义，为前端 toast 提供信息
        self.assertTrue(
            ("类别" in detail) or ("题目" in detail),
            f"[{case_label}] detail does not indicate category-has-no-content semantics: {detail!r}",
        )

    # --- Deterministic parameterized cases --------------------------------

    def test_c1_single_nonexistent_category_reproduces_bug(self):
        """C1: single category string not present in daily_content → bug."""
        response = self._post_generate({
            "mode": "theme",
            "category": ["nonexistent"],
            "question_count": 10,
        })
        self._assert_bug_condition_response(response, "C1_single_nonexistent")

    def test_c1_multi_category_all_miss_reproduces_bug(self):
        """C1: multi-category where every entry is absent from daily_content → bug."""
        response = self._post_generate({
            "mode": "theme",
            "category": ["ghost_a", "ghost_b"],
            "question_count": 5,
        })
        self._assert_bug_condition_response(response, "C1_multi_all_miss")

    def test_c2_category_matched_but_pool_empty_reproduces_bug(self):
        """C2: category matches a daily_content with zero phrases/words → bug."""
        response = self._post_generate({
            "mode": "theme",
            "category": [SEEDED_EMPTY_CATEGORY],
            "question_count": 5,
        })
        self._assert_bug_condition_response(response, "C2_pool_empty")

    # --- Scoped property-based tests --------------------------------------

    @hyp_settings(
        max_examples=25,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(
        # Hypothesis explores the C1 domain: non-empty lists of category
        # strings disjoint from seeded ones. We constrain to short ascii
        # labels to keep the search space deterministic.
        miss_cats=st.lists(
            st.text(
                alphabet=st.characters(
                    min_codepoint=ord("a"),
                    max_codepoint=ord("z"),
                ),
                min_size=3,
                max_size=12,
            ).filter(
                lambda s: s not in SEEDED_CATEGORIES_WITH_POOL
                and s != SEEDED_EMPTY_CATEGORY
            ),
            min_size=1,
            max_size=4,
            unique=True,
        ),
        question_count=st.integers(min_value=1, max_value=20),
    )
    def test_property_c1_any_unknown_category_reproduces_bug(self, miss_cats, question_count):
        """Property 1 — For every non-empty list of unseeded categories, the
        current implementation violates `expectedBehavior(response)`.

        Validates: Requirements 2.1
        """
        response = self._post_generate({
            "mode": "theme",
            "category": miss_cats,
            "question_count": question_count,
        })
        self._assert_bug_condition_response(
            response,
            f"C1_property miss_cats={miss_cats!r} qc={question_count}",
        )

    @hyp_settings(
        max_examples=10,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(question_count=st.integers(min_value=1, max_value=20))
    def test_property_c2_matched_empty_pool_reproduces_bug(self, question_count):
        """Property 1 — For every reasonable question_count, the fixed
        category=[SEEDED_EMPTY_CATEGORY] request violates `expectedBehavior`.

        Validates: Requirements 2.2
        """
        response = self._post_generate({
            "mode": "theme",
            "category": [SEEDED_EMPTY_CATEGORY],
            "question_count": question_count,
        })
        self._assert_bug_condition_response(
            response,
            f"C2_property qc={question_count}",
        )


if __name__ == "__main__":
    unittest.main()
