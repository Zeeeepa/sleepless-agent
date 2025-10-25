"""Shared helpers for reasoning about day/night windows."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

NIGHT_START_HOUR = 20  # 8 PM
NIGHT_END_HOUR = 8     # 8 AM


def is_nighttime(dt: Optional[datetime] = None) -> bool:
    """Return True when the provided datetime falls within the night window."""
    if dt is None:
        dt = datetime.utcnow()
    hour = dt.hour
    return hour >= NIGHT_START_HOUR or hour < NIGHT_END_HOUR


def get_time_label(dt: Optional[datetime] = None) -> str:
    """Return a human-readable label for the current time period."""
    return "night" if is_nighttime(dt) else "daytime"


def current_period_start(dt: Optional[datetime] = None) -> datetime:
    """Return the UTC timestamp marking the start of the current period."""
    dt = dt or datetime.utcnow()
    today = dt.replace(hour=0, minute=0, second=0, microsecond=0)

    if is_nighttime(dt):
        night_start = today.replace(hour=NIGHT_START_HOUR)
        if dt.hour < NIGHT_END_HOUR:
            night_start = (today - timedelta(days=1)).replace(hour=NIGHT_START_HOUR)
        return night_start

    return today.replace(hour=NIGHT_END_HOUR)


def rate_limit_for_time(
    *,
    day_limit: int,
    night_limit: int,
    dt: Optional[datetime] = None,
) -> int:
    """Return the appropriate rate limit for the provided time."""
    return night_limit if is_nighttime(dt) else day_limit
