# Profile Active Streak Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the profile page display a truthful continuous learning streak based on learning, review, and quiz activity.

**Architecture:** Extend the existing `/review/progress/summary` endpoint with derived activity fields while keeping legacy fields intact. The backend calculates Beijing-date activity from `learn_sessions`, `review_logs`, and `quiz_records`; the mini-program profile page displays the new canonical field with today activity subtext and falls back to `study_streak` for old backends.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, Python `unittest`, WeChat mini-program WXML/WXSS/JS.

---

## File Structure

- Modify `backend/app/schemas/user.py`: add response models for today's activity and new progress summary fields.
- Modify `backend/app/routers/review.py`: add helper functions and extend `/review/progress/summary`.
- Modify `backend/tests/test_review_quiz.py`: add backend regression tests for learning/review/quiz streak sources.
- Modify `miniprogram/pages/profile/profile.js`: map new fields and build display text.
- Modify `miniprogram/pages/profile/profile.wxml`: show canonical streak and subtext.
- Modify `miniprogram/pages/profile/profile.wxss`: make the profile streak card readable and stable on mobile.

## Task 1: Backend Contract And Calculation

**Files:**
- Modify: `backend/app/schemas/user.py`
- Modify: `backend/app/routers/review.py`
- Test: `backend/tests/test_review_quiz.py`

- [ ] Add `TodayActivity` to `backend/app/schemas/user.py` with `learn_sessions`, `review_items`, and `quiz_answers`.
- [ ] Extend `ProgressSummary` with `active_streak_days`, `last_active_date`, `today_activity`, and `streak_sources`.
- [ ] Add review-router helpers to convert timestamps to Beijing dates, aggregate source dates, calculate active streak days, and count today's activities.
- [ ] Extend `/review/progress/summary` to return the new fields without removing legacy fields.
- [ ] Add tests for no activity, single-source activity, mixed-source consecutive days, yesterday grace, and gap break.
- [ ] Run `DEBUG=false backend/venv/bin/python -m unittest backend.tests.test_review_quiz`.

## Task 2: Profile Page Mapping And UI

**Files:**
- Modify: `miniprogram/pages/profile/profile.js`
- Modify: `miniprogram/pages/profile/profile.wxml`
- Modify: `miniprogram/pages/profile/profile.wxss`

- [ ] Add a profile stat normalizer that prefers `active_streak_days` over `study_streak`.
- [ ] Build `streakSubtext` from `today_activity` and `last_active_date`.
- [ ] Update the first stats item to show `连续学习`, unit `天`, and the subtext.
- [ ] Replace emoji-based core stat icon in the streak block with a CSS mark.
- [ ] Add responsive styles so long streak subtext wraps inside the card.
- [ ] Run `node --check miniprogram/pages/profile/profile.js`.

## Task 3: Final Verification

**Files:**
- Verify backend and frontend changed files.

- [ ] Run backend focused tests.
- [ ] Run profile JS syntax check.
- [ ] Run `git diff --check` on changed backend/frontend files.
- [ ] Review the final diff for unrelated changes.
