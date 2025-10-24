"""Custom exceptions for Sleepless Agent"""

from datetime import datetime
from typing import Optional


class PauseException(Exception):
    """Raised when Pro plan usage limit requires task execution pause"""

    def __init__(
        self,
        message: str,
        reset_time: datetime,
        current_usage: int,
        usage_limit: int,
    ):
        """Initialize PauseException

        Args:
            message: Exception message
            reset_time: When usage limit will reset
            current_usage: Current messages used
            usage_limit: Messages limit per 5-hour window
        """
        super().__init__(message)
        self.reset_time = reset_time
        self.current_usage = current_usage
        self.usage_limit = usage_limit
        self.percent_used = (current_usage / usage_limit * 100) if usage_limit > 0 else 0
