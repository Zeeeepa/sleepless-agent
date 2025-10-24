"""Pro plan usage monitoring and checking"""

import re
import subprocess
from datetime import datetime, timedelta
from typing import Optional, Tuple

from loguru import logger


class ProPlanUsageChecker:
    """Check Claude Code Pro plan usage via CLI"""

    def __init__(self, command: str = "claude usage"):
        """Initialize usage checker

        Args:
            command: CLI command to run (default: "claude usage")
        """
        self.command = command
        self.last_check_time: Optional[datetime] = None
        self.cached_usage: Optional[Tuple[int, int, datetime]] = None
        self.cache_duration_seconds = 60

    def get_usage(self) -> Tuple[int, int, datetime]:
        """Execute CLI command and parse usage response

        Returns:
            Tuple of (messages_used, messages_limit, reset_time)

        Raises:
            RuntimeError: If command fails or output can't be parsed
        """
        try:
            # Check cache first (valid for 60 seconds)
            if self.cached_usage and self.last_check_time:
                cache_age = (datetime.utcnow() - self.last_check_time).total_seconds()
                if cache_age < self.cache_duration_seconds:
                    logger.debug(f"Using cached usage data (age: {cache_age:.0f}s)")
                    return self.cached_usage

            # Run CLI command
            result = subprocess.run(
                self.command.split(),
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                logger.error(f"Claude usage command failed: {result.stderr}")
                raise RuntimeError(f"Usage check failed: {result.stderr}")

            output = result.stdout + result.stderr

            output = output.strip()

            if not output:
                logger.warning(
                    "Claude usage command returned no output; falling back to cached or default usage data."
                )
                return self._fallback_usage()

            # Parse output
            try:
                messages_used, messages_limit, reset_time = self._parse_usage_output(output)
            except RuntimeError as parse_error:
                logger.warning(f"Could not interpret usage output: {parse_error}")
                return self._fallback_usage()

            # Cache result
            self.cached_usage = (messages_used, messages_limit, reset_time)
            self.last_check_time = datetime.utcnow()

            logger.info(
                f"Pro plan usage: {messages_used}/{messages_limit} "
                f"({messages_used/messages_limit*100:.1f}%) - resets at {reset_time.strftime('%H:%M:%S')}"
            )

            return messages_used, messages_limit, reset_time

        except subprocess.TimeoutExpired:
            logger.error("Usage check timed out after 10 seconds")
            raise RuntimeError("Usage check timed out")
        except RuntimeError:
            raise
        except Exception as e:
            logger.error(f"Failed to get usage: {e}")
            raise

    def _parse_usage_output(self, output: str) -> Tuple[int, int, datetime]:
        """Parse 'claude usage' command output

        Handles multiple output formats:
        - "61% used" (Claude Code CLI format) - estimates count from percentage
        - "You have used 28 of 40 messages. Resets in 2 hours 45 minutes."
        - "Messages: 28/40 (70%)"
        - "Usage: 28 messages used, 12 remaining"

        Args:
            output: Raw output from claude usage command

        Returns:
            Tuple of (messages_used, messages_limit, reset_time)

        Raises:
            RuntimeError: If output format can't be parsed
        """
        lines = output.strip().split("\n")

        messages_used = None
        messages_limit = None
        reset_time = None

        # Try format 0: "61% used" (Claude Code CLI output)
        # This is the primary format for `claude /usage`
        for line in lines:
            match = re.search(r'(\d+)%\s+used', line, re.IGNORECASE)
            if match:
                percent_used = int(match.group(1))
                # Estimate counts based on typical Pro plan limit (40 messages)
                # This is for display/calculation purposes only
                messages_limit = 40  # Standard Pro plan limit per 5-hour window
                messages_used = int((percent_used / 100.0) * messages_limit)
                logger.debug(f"Parsed percentage format: {percent_used}% used → ~{messages_used}/{messages_limit}")
                break

        # Try format 1: "You have used 28 of 40 messages"
        if messages_used is None:
            for line in lines:
                match = re.search(r"used\s+(\d+)\s+of\s+(\d+)\s+messages", line, re.IGNORECASE)
                if match:
                    messages_used = int(match.group(1))
                    messages_limit = int(match.group(2))
                    logger.debug(f"Parsed format 1: {messages_used}/{messages_limit}")
                    break

        # Try format 2: "Messages: 28/40"
        if messages_used is None:
            for line in lines:
                match = re.search(r"Messages?:\s*(\d+)/(\d+)", line, re.IGNORECASE)
                if match:
                    messages_used = int(match.group(1))
                    messages_limit = int(match.group(2))
                    logger.debug(f"Parsed format 2: {messages_used}/{messages_limit}")
                    break

        # Try format 3: "28 messages used, 12 remaining"
        if messages_used is None:
            for line in lines:
                match = re.search(r"(\d+)\s+messages?\s+used", line, re.IGNORECASE)
                if match:
                    messages_used = int(match.group(1))

                    # Find remaining
                    remaining_match = re.search(r"(\d+)\s+remaining", line, re.IGNORECASE)
                    if remaining_match:
                        remaining = int(remaining_match.group(1))
                        messages_limit = messages_used + remaining
                        logger.debug(f"Parsed format 3: {messages_used}/{messages_limit}")
                    break

        if messages_used is None or messages_limit is None:
            displayed = output.replace("\n", " ").strip()
            if len(displayed) > 120:
                displayed = f"{displayed[:117]}..."
            raise RuntimeError(f"Could not parse usage from '{displayed}'")

        # Parse reset time
        reset_time = self._parse_reset_time(output)

        if reset_time is None:
            # Fallback: assume 5 hour window
            logger.warning("Could not parse reset time, assuming 5 hour window")
            reset_time = datetime.utcnow() + timedelta(hours=5)

        return messages_used, messages_limit, reset_time

    def _parse_reset_time(self, output: str) -> Optional[datetime]:
        """Parse reset time from output

        Formats:
        - "Resets 2:59am (America/New_York)" (Claude Code CLI format)
        - "Resets in 2 hours 45 minutes"
        - "Resets in 3h 15m"
        - "Next reset: 14:30 UTC"

        Args:
            output: Raw output string

        Returns:
            datetime of reset, or None if can't parse
        """
        # Try: "Resets 2:59am (America/New_York)" (Claude Code CLI format)
        # This is the primary format from `claude /usage`
        match = re.search(
            r'Resets\s+(\d{1,2}):(\d{2})(am|pm)\s+\(([^)]+)\)',
            output,
            re.IGNORECASE,
        )
        if match:
            try:
                hour = int(match.group(1))
                minute = int(match.group(2))
                meridiem = match.group(3).lower()
                timezone_str = match.group(4)  # e.g., "America/New_York"

                # Convert 12-hour to 24-hour format
                if meridiem == 'pm' and hour != 12:
                    hour += 12
                elif meridiem == 'am' and hour == 12:
                    hour = 0

                # Create reset time (assume same day, or next day if in past)
                reset_time = datetime.utcnow().replace(
                    hour=hour, minute=minute, second=0, microsecond=0
                )

                # If reset time is in past, add 1 day
                if reset_time < datetime.utcnow():
                    reset_time += timedelta(days=1)

                logger.debug(
                    f"Parsed reset time: {hour:02d}:{minute:02d} "
                    f"({meridiem}) {timezone_str} → {reset_time.strftime('%Y-%m-%d %H:%M:%S')}"
                )
                return reset_time
            except ValueError as e:
                logger.warning(f"Failed to parse timezone format reset time: {e}")
                pass

        # Try: "Resets in X hours Y minutes"
        match = re.search(
            r"Resets?\s+in\s+(\d+)\s*(?:hours?|h)?\s+(\d+)\s*(?:minutes?|m)?",
            output,
            re.IGNORECASE,
        )
        if match:
            hours = int(match.group(1))
            minutes = int(match.group(2))
            return datetime.utcnow() + timedelta(hours=hours, minutes=minutes)

        # Try: "Resets in 3h"
        match = re.search(r"Resets?\s+in\s+(\d+)\s*h", output, re.IGNORECASE)
        if match:
            hours = int(match.group(1))
            return datetime.utcnow() + timedelta(hours=hours)

        # Try: "Resets in 45m"
        match = re.search(r"Resets?\s+in\s+(\d+)\s*m", output, re.IGNORECASE)
        if match:
            minutes = int(match.group(1))
            return datetime.utcnow() + timedelta(minutes=minutes)

        # Try: "Next reset: 14:30"
        match = re.search(r"Next\s+reset[:\s]+(\d{1,2}):(\d{2})", output, re.IGNORECASE)
        if match:
            try:
                hour = int(match.group(1))
                minute = int(match.group(2))
                reset_time = datetime.utcnow().replace(hour=hour, minute=minute, second=0, microsecond=0)

                # If time is in past, add 1 day
                if reset_time < datetime.utcnow():
                    reset_time += timedelta(days=1)

                return reset_time
            except ValueError:
                pass

        return None

    def check_should_pause(self, threshold_percent: float = 85.0) -> Tuple[bool, Optional[datetime]]:
        """Check if usage exceeds threshold

        Args:
            threshold_percent: Pause if usage >= this percent (default 85%)

        Returns:
            Tuple of (should_pause: bool, reset_time: datetime or None)
        """
        try:
            messages_used, messages_limit, reset_time = self.get_usage()
            percent_used = (messages_used / messages_limit * 100) if messages_limit > 0 else 0

            should_pause = percent_used >= threshold_percent

            if should_pause:
                logger.warning(
                    f"Usage threshold exceeded: {messages_used}/{messages_limit} "
                    f"({percent_used:.1f}% >= {threshold_percent}%)"
                )

            return should_pause, reset_time

        except Exception as e:
            logger.error(f"Error checking threshold: {e}")
            # Return False to not pause on error
            return False, None

    def _fallback_usage(self) -> Tuple[int, int, datetime]:
        """
        Provide cached usage if available, otherwise return a conservative default.
        """
        if self.cached_usage and self.last_check_time:
            logger.debug("Using cached usage data after failed usage command.")
            return self.cached_usage

        reset_time = datetime.utcnow() + timedelta(hours=5)
        fallback = (0, 40, reset_time)
        self.cached_usage = fallback
        self.last_check_time = datetime.utcnow()
        logger.info(
            "Defaulting to 0/40 usage with 5-hour reset window due to missing usage data."
        )
        return fallback
