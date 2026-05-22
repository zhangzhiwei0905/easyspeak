# Profile Active Learning Streak Design

## Summary

The profile page should show a truthful `连续学习天数` based on real user activity across learning, review, and quiz flows. The metric should represent consecutive active learning days, not only the legacy `users.study_streak` counter.

## Goals

- Count a day as active when the user completes at least one meaningful learning action.
- Include three activity sources: learning sessions, review completions, and quiz submissions.
- Use a single timezone rule, `Asia/Shanghai`, for all day and week boundaries.
- Keep existing API consumers working while giving the profile page a clearer field to display.
- Make the UI feel like a light learning dashboard: clear, calm, and honest.

## Non-Goals

- No new standalone achievement system in this change.
- No user-customizable streak rules.
- No migration that rewrites historical user counters.
- No simulated progress, fake trend lines, or placeholder statistics.

## Current State

The profile page currently calls `/review/progress/summary` and maps `study_streak` into `stats.studyStreak`. The backend returns `study_streak` from `users.study_streak`.

That counter is updated by:

- `/learn/report`, when a learning session report is submitted.
- `/review/complete`, when a review item is completed.

Quiz-only activity is not included in `users.study_streak`, even though quiz activity is recorded in `quiz_records` and already powers quiz statistics.

## Recommended Metric

`active_streak_days` is the canonical profile streak.

A user has an active learning day if, in Beijing time, that natural day contains at least one of:

- A `learn_sessions` row for the user.
- A `review_logs` row for the user.
- A `quiz_records` row for the user.

Multiple actions on the same day count as one active day for the streak, but action counts remain useful for profile subtext.

## Streak Calculation

Use `Asia/Shanghai` for all date conversion.

1. Collect distinct activity dates from the three source tables for the current user.
2. Convert each timestamp to a Beijing natural date.
3. Choose the anchor date:
   - If today is active, anchor on today.
   - If today is not active but yesterday is active, anchor on yesterday.
   - Otherwise return `0`.
4. Walk backward by one day at a time while each date exists in the activity-date set.
5. Return the count as `active_streak_days`.

This keeps the streak from disappearing early in the day before the user has had a chance to practice.

## API Design

Extend `/review/progress/summary` without removing legacy fields.

Add:

```json
{
  "active_streak_days": 5,
  "last_active_date": "2026-05-22",
  "today_activity": {
    "learn_sessions": 1,
    "review_items": 3,
    "quiz_answers": 12
  },
  "streak_sources": ["learn", "review", "quiz"]
}
```

Field meanings:

- `active_streak_days`: canonical profile streak.
- `last_active_date`: latest active Beijing date, or `null` if no activity exists.
- `today_activity.learn_sessions`: number of learning session reports today.
- `today_activity.review_items`: number of review completion logs today.
- `today_activity.quiz_answers`: number of quiz answer records today.
- `streak_sources`: activity types present on the latest active date.

Keep:

- `study_streak`: legacy field from `users.study_streak`.
- `total_study_days`, `mastered_phrases`, `mastered_words`, `total_quiz`, `avg_accuracy`.

The profile page should display `active_streak_days` when available and fall back to `study_streak` only for older backend compatibility.

## UI Design

The profile stats card should keep the existing learning dashboard direction but make the streak card more explanatory.

Primary display:

- Label: `连续学习`
- Value: `{active_streak_days}`
- Unit: `天`

Subtext states:

- Today active: `今日已完成：学习 {n} 次 · 复习 {n} 项 · 测验 {n} 题`
- Today inactive but yesterday active: `连续保持中，今天完成一次练习即可续上`
- No current streak: `今天完成一次学习即可重新开始连续记录`

Visual direction:

- Light background, white cards, blue-green primary palette, small warm accent for reminders.
- Use simple CSS or existing icon resources instead of emoji as core icons.
- Avoid fake trend bars. Only show counts backed by API data.
- Keep mobile layout stable at narrow widths. Long activity subtext should wrap cleanly.

## Data Flow

1. User opens profile page.
2. Frontend calls `/review/progress/summary`.
3. Backend aggregates current user's learning, review, and quiz activity dates.
4. Backend returns both legacy and new streak fields.
5. Frontend maps:
   - `active_streak_days` -> profile `连续学习`
   - `today_activity` -> streak subtext
   - old `study_streak` -> fallback only

If the API request fails, frontend may use local fallback, but the UI should make no stronger claim than the available data supports.

## Edge Cases

- No records in any source table: streak is `0`, `last_active_date` is `null`, all today counts are `0`.
- Multiple actions on the same day: streak day count increases by `1`, today activity counts show actual counts.
- Quiz-only day: counts as an active learning day.
- Review-only day: counts as an active learning day.
- Learning-only day: counts as an active learning day.
- Today inactive, yesterday active: show the existing streak through yesterday.
- Today and yesterday inactive: current streak is `0`.
- Naive UTC timestamps and timezone-aware timestamps should both be converted safely to Beijing dates.

## Testing

Backend tests:

- No activity returns `active_streak_days=0`.
- Learning-only activity counts toward streak.
- Review-only activity counts toward streak.
- Quiz-only activity counts toward streak.
- Same-day multiple sources count as one streak day.
- Consecutive multi-day mixed activity returns the correct count.
- One-day gap breaks the streak.
- Today inactive but yesterday active preserves the streak through yesterday.
- Beijing timezone boundary is respected.

Frontend checks:

- Profile uses `active_streak_days` before `study_streak`.
- Empty API data displays `0 天`.
- Today activity subtext handles zero and non-zero counts.
- Long subtext wraps inside the profile card without horizontal overflow.

## Implementation Notes

- Prefer a small backend helper such as `_calculate_active_streak_days(...)` rather than embedding the calculation directly in the route body.
- Keep the existing `/review/progress/summary` route to avoid a broader frontend API migration.
- Do not update `users.study_streak` from quiz submissions in this design; it remains a legacy compatibility field.
- The same aggregation helper can later support achievements such as `连续学习 7 天`.
