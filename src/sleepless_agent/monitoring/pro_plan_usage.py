"""Pro plan usage monitoring and checking"""

import os
import re
import shlex
import string
import subprocess
import sys
import time
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

try:  # pragma: no cover - platform dependent
    import pty
except (ImportError, AttributeError):
    pty = None  # type: ignore[misc,assignment]

if pty is not None:  # pragma: no cover - platform dependent
    import select
else:  # pragma: no cover - platform dependent
    select = None  # type: ignore[assignment]

from loguru import logger
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


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

            try:
                command_args = tuple(shlex.split(self.command))
            except ValueError as exc:
                logger.error(f"Invalid usage command '{self.command}': {exc}")
                return self._fallback_usage()

            raw_output, return_code = self._execute_command(command_args)
            cleaned_output = self._clean_command_output(raw_output)

            # Check for errors
            if return_code not in (0, -15, -9):  # 0 = success, -15 = SIGTERM, -9 = SIGKILL
                if cleaned_output:
                    logger.warning(
                        "Claude usage command returned non-zero exit code: "
                        f"{return_code}"
                    )
                else:
                    logger.error(
                        "Claude usage command failed with return code: "
                        f"{return_code}"
                    )

            if not cleaned_output:
                logger.warning(
                    "Claude usage command returned no output; falling back to cached or default usage data."
                )
                return self._fallback_usage()

            # Parse output
            try:
                messages_used, messages_limit, reset_time = self._parse_usage_output(cleaned_output)
            except RuntimeError as parse_error:
                logger.warning(f"Could not interpret usage output: {parse_error}")
                return self._fallback_usage()

            # Cache result
            self.cached_usage = (messages_used, messages_limit, reset_time)
            self.last_check_time = datetime.utcnow()

            # Note: 85% threshold is used by scheduler to decide whether to generate new tasks
            logger.info(
                f"Pro plan usage: {messages_used}/{messages_limit} "
                f"({messages_used/messages_limit*100:.1f}% / 85% pause threshold) - resets at {reset_time.strftime('%H:%M:%S')}"
            )

            return messages_used, messages_limit, reset_time

        except RuntimeError:
            raise
        except Exception as e:
            logger.error(f"Failed to get usage: {e}")
            raise

    def _execute_command(self, command_args: Tuple[str, ...]) -> Tuple[str, int]:
        """Execute the configured CLI command and capture combined output."""

        # Attempt PTY capture first to support interactive commands like "claude /usage".
        if self._supports_pty():
            with suppress(Exception):
                return self._execute_with_pty(command_args)

        # Fall back to the simpler pipe-based execution.
        return self._execute_with_pipes(command_args)

    def _execute_with_pipes(self, command_args: Tuple[str, ...]) -> Tuple[str, int]:
        """Fallback execution path using plain stdout/stderr pipes."""

        process = subprocess.Popen(
            command_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        output = ""
        stderr_output = ""
        try:
            output, stderr_output = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            logger.debug("Usage command still running after 5s, terminating process (pipe mode)")
            process.terminate()
            try:
                output, stderr_output = process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                output, stderr_output = process.communicate()

        combined_output = (output or "") + (stderr_output or "")
        return combined_output, process.returncode

    def _execute_with_pty(self, command_args: Tuple[str, ...]) -> Tuple[str, int]:
        """Execute the CLI command inside a PTY to capture interactive output."""

        if not self._supports_pty():
            raise RuntimeError("Pseudo-terminal capture not supported on this platform.")

        master_fd, slave_fd = pty.openpty()
        env = os.environ.copy()
        env.setdefault("TERM", "xterm-256color")

        process = subprocess.Popen(
            command_args,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            env=env,
            close_fds=True,
        )

        os.close(slave_fd)

        buffer: list[bytes] = []
        os.set_blocking(master_fd, False)

        try:
            capture_deadline = time.monotonic() + 5
            while time.monotonic() < capture_deadline:
                if process.poll() is not None:
                    break

                ready, _, _ = select.select([master_fd], [], [], 0.1)
                if master_fd in ready:
                    try:
                        chunk = os.read(master_fd, 4096)
                    except OSError:
                        break

                    if not chunk:
                        break

                    buffer.append(chunk)

                    decoded = chunk.decode("utf-8", errors="ignore")
                    if "Resets" in decoded or "% used" in decoded:
                        # Slow down reading once we've seen the usage screen.
                        capture_deadline = min(capture_deadline, time.monotonic() + 0.5)

            # Request the CLI to exit gracefully (Esc), fallback to Ctrl+C/terminate if needed.
            with suppress(OSError):
                os.write(master_fd, b"\x1b")
            time.sleep(0.2)

            if process.poll() is None:
                with suppress(OSError):
                    os.write(master_fd, b"\x03")  # Ctrl+C
                time.sleep(0.2)

            if process.poll() is None:
                process.terminate()

            with suppress(subprocess.TimeoutExpired):
                process.wait(timeout=2)

            if process.poll() is None:
                process.kill()
                process.wait(timeout=2)

            # Drain any trailing output.
            drain_deadline = time.monotonic() + 0.5
            while time.monotonic() < drain_deadline:
                ready, _, _ = select.select([master_fd], [], [], 0.1)
                if master_fd not in ready:
                    break
                try:
                    chunk = os.read(master_fd, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                buffer.append(chunk)
        finally:
            os.close(master_fd)

        combined = b"".join(buffer)
        return combined.decode("utf-8", errors="ignore"), process.returncode

    @staticmethod
    def _supports_pty() -> bool:
        """Detect whether PTY capture is supported on this platform."""
        if pty is None or select is None:
            return False
        if sys.platform.startswith("win"):  # Windows lacks native PTY support.
            return False
        return True

    @staticmethod
    def _clean_command_output(raw_output: str) -> str:
        """Strip ANSI/tui control sequences and non-printable characters."""

        if not raw_output:
            return ""

        text = raw_output.replace("\r", "\n")

        ansi_escape = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
        osc_escape = re.compile(r"\x1B\][^\x07]*(\x07|\x1B\\)")

        text = ansi_escape.sub("", text)
        text = osc_escape.sub("", text)

        printable = set(string.printable + "\n")
        text = ''.join(ch if ch in printable else ' ' for ch in text)

        lines = [line.rstrip() for line in text.splitlines()]
        cleaned_lines = [line for line in lines if line.strip()]

        return "\n".join(cleaned_lines)

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
        def _convert_with_timezone(hour: int, minute: int, second: int, tz_label: Optional[str]) -> Optional[datetime]:
            if not tz_label:
                return None

            label = tz_label.strip()
            if not label:
                return None

            if label.upper() in {"UTC", "GMT"}:
                tzinfo = timezone.utc
            else:
                try:
                    tzinfo = ZoneInfo(label)
                except ZoneInfoNotFoundError:
                    return None

            local_now = datetime.now(tz=tzinfo)
            reset_local = local_now.replace(hour=hour % 24, minute=minute, second=second, microsecond=0)
            if reset_local < local_now:
                reset_local += timedelta(days=1)
            return reset_local.astimezone(timezone.utc).replace(tzinfo=None)

        # Try: "Resets 2:59am (America/New_York)" or "Resets 7pm (America/New_York)"
        match = re.search(
            r"Resets\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)\s+\(([^)]+)\)",
            output,
            re.IGNORECASE,
        )
        if match:
            try:
                hour = int(match.group(1))
                minute = int(match.group(2)) if match.group(2) else 0
                meridiem = match.group(3).lower()
                timezone_str = match.group(4)  # e.g., "America/New_York"

                if meridiem == "pm" and hour != 12:
                    hour += 12
                elif meridiem == "am" and hour == 12:
                    hour = 0

                reset_time = _convert_with_timezone(hour, minute, 0, timezone_str)
                if reset_time is None:
                    reset_time = datetime.utcnow().replace(
                        hour=hour % 24, minute=minute, second=0, microsecond=0
                    )

                if reset_time < datetime.utcnow():
                    reset_time += timedelta(days=1)

                logger.debug(
                    f"Parsed reset time: {hour % 24:02d}:{minute:02d} "
                    f"({meridiem}) {timezone_str} → {reset_time.strftime('%Y-%m-%d %H:%M:%S')}"
                )
                return reset_time
            except ValueError as exc:
                logger.warning(f"Failed to parse timezone format reset time: {exc}")

        # Try: "Resets at 00:24" or "Resets @ 00:24:59 UTC"
        match = re.search(
            r"Resets?\s+(?:at|@)\s+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(am|pm)?(?:\s+\(([^)]+)\)|\s+(UTC|GMT|[A-Za-z/_-]+))?",
            output,
            re.IGNORECASE,
        )
        if match:
            try:
                hour = int(match.group(1))
                minute = int(match.group(2))
                second = int(match.group(3)) if match.group(3) else 0
                meridiem = match.group(4).lower() if match.group(4) else None
                timezone_str = match.group(5) or match.group(6)

                if meridiem:
                    if meridiem == "pm" and hour != 12:
                        hour += 12
                    elif meridiem == "am" and hour == 12:
                        hour = 0

                reset_time = _convert_with_timezone(hour, minute, second, timezone_str)
                if reset_time is None:
                    reset_time = datetime.utcnow().replace(
                        hour=hour % 24, minute=minute, second=second, microsecond=0
                    )
                if reset_time < datetime.utcnow():
                    reset_time += timedelta(days=1)
                return reset_time
            except ValueError:
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
        match = re.search(
            r"Next\s+reset[:\s]+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(UTC|GMT)?",
            output,
            re.IGNORECASE,
        )
        if match:
            try:
                hour = int(match.group(1))
                minute = int(match.group(2))
                second = int(match.group(3)) if match.group(3) else 0
                timezone_str = match.group(4)
                reset_time = _convert_with_timezone(hour, minute, second, timezone_str)
                if reset_time is None:
                    reset_time = datetime.utcnow().replace(
                        hour=hour % 24, minute=minute, second=second, microsecond=0
                    )

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
