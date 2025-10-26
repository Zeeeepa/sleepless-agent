"""Shared formatting utilities for human-readable status output."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def format_duration(seconds: Optional[float]) -> str:
    """Turn seconds into a compact human-readable duration string."""
    if seconds is None:
        return "—"

    seconds = int(abs(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)

    parts: list[str] = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)


def relative_time(dt: Optional[datetime], default: str = "—") -> str:
    """Return relative time string compared to now (e.g., '5m ago')."""
    if not dt:
        return default

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    delta = now - dt
    suffix = "ago"
    total_seconds = delta.total_seconds()

    if total_seconds < 0:
        total_seconds = -total_seconds
        suffix = "from now"

    return f"{format_duration(total_seconds)} {suffix}"


def shorten(text: str, limit: int = 120) -> str:
    """Compress whitespace and truncate to a limit with ellipsis."""
    clean = " ".join(text.strip().split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "…"


def format_age_seconds(seconds: Optional[float], default: str = "N/A") -> str:
    """Format seconds representing age (time elapsed) with 'ago' suffix."""
    if seconds is None:
        return default
    return f"{format_duration(seconds)} ago"


__all__ = [
    "format_duration",
    "relative_time",
    "shorten",
    "format_age_seconds",
]
