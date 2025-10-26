"""Shared helpers for reasoning about day/night windows."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

NIGHT_START_HOUR = 20  # 8 PM
NIGHT_END_HOUR = 8     # 8 AM


def is_nighttime(
    dt: Optional[datetime] = None,
    night_start_hour: int = NIGHT_START_HOUR,
    night_end_hour: int = NIGHT_END_HOUR,
) -> bool:
    """Return True when the provided datetime falls within the night window."""
    if dt is None:
        dt = datetime.now()
    hour = dt.hour

    if night_start_hour < night_end_hour:
        # Same-day period (e.g., 1 AM to 9 AM)
        return night_start_hour <= hour < night_end_hour
    else:
        # Cross-midnight period (e.g., 8 PM to 8 AM)
        return hour >= night_start_hour or hour < night_end_hour


def get_time_label(
    dt: Optional[datetime] = None,
    night_start_hour: int = NIGHT_START_HOUR,
    night_end_hour: int = NIGHT_END_HOUR,
) -> str:
    """Return a human-readable label for the current time period."""
    return "night" if is_nighttime(dt, night_start_hour, night_end_hour) else "daytime"


def current_period_start(
    dt: Optional[datetime] = None,
    night_start_hour: int = NIGHT_START_HOUR,
    night_end_hour: int = NIGHT_END_HOUR,
) -> datetime:
    """Return the local timestamp marking the start of the current period."""
    dt = dt or datetime.now()
    today = dt.replace(hour=0, minute=0, second=0, microsecond=0)

    if is_nighttime(dt, night_start_hour, night_end_hour):
        if night_start_hour < night_end_hour:
            # Same-day nighttime (e.g., 1 AM to 9 AM) - period starts at night_start_hour today
            return today.replace(hour=night_start_hour)
        else:
            # Cross-midnight nighttime (e.g., 8 PM to 8 AM)
            if dt.hour >= night_start_hour:
                # Before midnight: period starts today at night_start_hour
                return today.replace(hour=night_start_hour)
            else:
                # After midnight: period starts yesterday at night_start_hour
                return (today - timedelta(days=1)).replace(hour=night_start_hour)

    # Daytime period starts at night_end_hour today
    return today.replace(hour=night_end_hour)
