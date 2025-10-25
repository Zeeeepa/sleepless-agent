"""Custom exceptions for Sleepless Agent"""

from datetime import datetime
from typing import Optional


class PauseException(Exception):
    """Raised when Pro plan usage limit requires task execution pause"""

    def __init__(
        self,
        message: str,
        reset_time: Optional[datetime],
        usage_percent: float,
    ):
        """Initialize PauseException

        Args:
            message: Exception message
            reset_time: When usage limit will reset
            usage_percent: Usage percentage reported by CLI
        """
        super().__init__(message)
        self.reset_time = reset_time
        self.usage_percent = usage_percent
