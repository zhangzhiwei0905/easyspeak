"""Shared spaced repetition helpers."""

from datetime import datetime, timedelta


def calculate_next_review_at(mastery: int, review_count: int, now: datetime) -> datetime:
    """Calculate the next review timestamp from the latest mastery result."""
    intervals = {
        0: 1,
        1: 1,
        2: 2,
        3: 5,
        4: 14,
        5: 30,
    }
    base_interval = intervals.get(mastery, 1)

    if review_count > 1 and mastery >= 3:
        base_interval = int(base_interval * (1.3 ** min(review_count - 1, 5)))

    return now + timedelta(days=min(base_interval, 90))
