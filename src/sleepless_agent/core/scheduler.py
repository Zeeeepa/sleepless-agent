"""Smart task scheduler with usage tracking and time-based quotas"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Tuple

from loguru import logger
from sqlalchemy.orm import Session

from .models import Task, TaskPriority, TaskStatus, UsageMetric
from .task_queue import TaskQueue


class TimeOfDay:
    """Classify time of day for budget allocation"""

    NIGHT_START_HOUR = 20  # 8 PM
    NIGHT_END_HOUR = 8  # 8 AM

    @classmethod
    def is_nighttime(cls, dt: Optional[datetime] = None) -> bool:
        """Check if given datetime is nighttime (8 PM - 8 AM)"""
        if dt is None:
            dt = datetime.utcnow()

        hour = dt.hour
        # Night: 20-23 or 0-7
        return hour >= cls.NIGHT_START_HOUR or hour < cls.NIGHT_END_HOUR

    @classmethod
    def get_time_label(cls, dt: Optional[datetime] = None) -> str:
        """Get human-readable time label"""
        return "night" if cls.is_nighttime(dt) else "daytime"


class BudgetManager:
    """Manage daily/monthly budgets with time-based allocation"""

    def __init__(
        self,
        session: Session,
        daily_budget_usd: float = 10.0,
        night_quota_percent: float = 90.0,
    ):
        """Initialize budget manager

        Args:
            session: Database session for querying usage
            daily_budget_usd: Daily budget in USD (default: $10)
            night_quota_percent: Percentage of daily budget for nighttime (default: 90%)
        """
        self.session = session
        self.daily_budget_usd = Decimal(str(daily_budget_usd))
        self.night_quota_percent = Decimal(str(night_quota_percent))
        self.day_quota_percent = Decimal("100") - self.night_quota_percent

    def get_usage_in_period(
        self, start_time: datetime, end_time: Optional[datetime] = None
    ) -> Decimal:
        """Get total usage in USD for a time period"""
        if end_time is None:
            end_time = datetime.utcnow()

        metrics = (
            self.session.query(UsageMetric)
            .filter(
                UsageMetric.created_at >= start_time,
                UsageMetric.created_at < end_time,
            )
            .all()
        )

        total = Decimal("0")
        for metric in metrics:
            if metric.total_cost_usd:
                try:
                    total += Decimal(metric.total_cost_usd)
                except Exception as e:
                    logger.warning(f"Failed to parse cost {metric.total_cost_usd}: {e}")

        return total

    def get_today_usage(self) -> Decimal:
        """Get total usage for today (UTC midnight to now)"""
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        return self.get_usage_in_period(today_start)

    def get_current_time_period_usage(self) -> Decimal:
        """Get usage for current time period (night or day)"""
        now = datetime.utcnow()
        is_night = TimeOfDay.is_nighttime(now)

        if is_night:
            # Night period: either from 8 PM yesterday or midnight today
            today = now.replace(hour=0, minute=0, second=0, microsecond=0)
            night_start = today.replace(hour=TimeOfDay.NIGHT_START_HOUR)

            # If before 8 AM, night started yesterday
            if now.hour < TimeOfDay.NIGHT_END_HOUR:
                night_start = (today - timedelta(days=1)).replace(
                    hour=TimeOfDay.NIGHT_START_HOUR
                )

            return self.get_usage_in_period(night_start)
        else:
            # Day period: 8 AM to 8 PM today
            today = now.replace(hour=0, minute=0, second=0, microsecond=0)
            day_start = today.replace(hour=TimeOfDay.NIGHT_END_HOUR)
            return self.get_usage_in_period(day_start)

    def get_current_quota(self) -> Decimal:
        """Get budget quota for current time period"""
        is_night = TimeOfDay.is_nighttime()

        if is_night:
            quota = self.daily_budget_usd * (self.night_quota_percent / Decimal("100"))
        else:
            quota = self.daily_budget_usd * (self.day_quota_percent / Decimal("100"))

        return quota

    def get_remaining_budget(self) -> Decimal:
        """Get remaining budget for current time period"""
        quota = self.get_current_quota()
        usage = self.get_current_time_period_usage()
        remaining = quota - usage
        return max(Decimal("0"), remaining)

    def is_budget_available(self, estimated_cost: Decimal = Decimal("0.50")) -> bool:
        """Check if budget is available for a task

        Args:
            estimated_cost: Estimated cost in USD (default: $0.50 per task)

        Returns:
            True if budget available, False otherwise
        """
        remaining = self.get_remaining_budget()
        return remaining >= estimated_cost

    def get_usage_percent(self) -> int:
        """Get current usage as percentage of current quota (0-100)"""
        quota = self.get_current_quota()
        usage = self.get_current_time_period_usage()

        if quota == 0:
            return 0

        percent = (usage / quota) * 100
        return min(100, int(percent))

    def get_budget_status(self) -> dict:
        """Get comprehensive budget status"""
        is_night = TimeOfDay.is_nighttime()
        time_label = TimeOfDay.get_time_label()

        quota = self.get_current_quota()
        usage = self.get_current_time_period_usage()
        remaining = self.get_remaining_budget()
        today_usage = self.get_today_usage()

        return {
            "time_period": time_label,
            "is_nighttime": is_night,
            "daily_budget_usd": float(self.daily_budget_usd),
            "current_quota_usd": float(quota),
            "current_usage_usd": float(usage),
            "remaining_budget_usd": float(remaining),
            "today_total_usage_usd": float(today_usage),
            "quota_allocation": {
                "night_percent": float(self.night_quota_percent),
                "day_percent": float(self.day_quota_percent),
            },
        }


class CreditWindow:
    """Tracks credit usage in 5-hour windows (legacy, kept for backwards compatibility)"""

    WINDOW_SIZE_HOURS = 5

    def __init__(self, start_time: Optional[datetime] = None):
        """Initialize credit window"""
        if start_time is None:
            start_time = datetime.utcnow()

        self.start_time = start_time
        self.end_time = start_time + timedelta(hours=self.WINDOW_SIZE_HOURS)
        self.tasks_executed = 0
        self.estimated_credits_used = 0

    def is_active(self) -> bool:
        """Check if window is still active"""
        return datetime.utcnow() < self.end_time

    def time_remaining_minutes(self) -> int:
        """Get minutes remaining in window"""
        remaining = (self.end_time - datetime.utcnow()).total_seconds() / 60
        return max(0, int(remaining))

    def __repr__(self):
        return f"<CreditWindow({self.tasks_executed} tasks, {self.time_remaining_minutes()}m left)>"


class SmartScheduler:
    """Intelligent task scheduler with budget management and time-based quotas"""

    def __init__(
        self,
        task_queue: TaskQueue,
        max_parallel_tasks: int = 3,
        daily_budget_usd: float = 10.0,
        night_quota_percent: float = 90.0,
        use_live_usage_check: bool = True,
        usage_command: str = "claude /usage",
        pause_threshold_percent: float = 85.0,
    ):
        """Initialize scheduler

        Args:
            task_queue: Task queue instance
            max_parallel_tasks: Maximum parallel tasks (default: 3)
            daily_budget_usd: Daily budget in USD (default: $10)
            night_quota_percent: Percentage for night usage (default: 90%)
            use_live_usage_check: Use live Pro plan usage check instead of budget estimate (default: True)
            usage_command: CLI command to check usage (default: "claude /usage")
            pause_threshold_percent: Pause scheduling if usage >= this percent (default: 85%)
        """
        self.task_queue = task_queue
        self.max_parallel_tasks = max_parallel_tasks
        self.use_live_usage_check = use_live_usage_check
        self.usage_command = usage_command
        self.pause_threshold_percent = pause_threshold_percent

        # Budget management with time-based allocation
        session = self.task_queue.SessionLocal()
        self.budget_manager = BudgetManager(
            session=session,
            daily_budget_usd=daily_budget_usd,
            night_quota_percent=night_quota_percent,
        )

        # Pro plan usage checker
        self.usage_checker = None
        if self.use_live_usage_check:
            try:
                from sleepless_agent.monitoring.pro_plan_usage import ProPlanUsageChecker
                self.usage_checker = ProPlanUsageChecker(command=usage_command)
                logger.info("Initialized live Pro plan usage checker")
            except ImportError:
                logger.warning("ProPlanUsageChecker not available, will fall back to budget-based check")
                self.use_live_usage_check = False

        # Legacy credit window support
        self.active_windows: List[CreditWindow] = []
        self.current_window: Optional[CreditWindow] = None
        self._init_current_window()
        self._last_budget_exhausted_log: Optional[datetime] = None
        self._budget_exhausted_logged = False
        self.usage_pause_until: Optional[datetime] = None
        self._usage_pause_grace = timedelta(minutes=1)
        self._usage_pause_default = timedelta(minutes=5)

    def _init_current_window(self):
        """Initialize current credit window"""
        now = datetime.utcnow()

        # Check if we need a new window
        if not self.current_window or not self.current_window.is_active():
            self.current_window = CreditWindow(start_time=now)
            self.active_windows.append(self.current_window)
            logger.info(f"New credit window started: {self.current_window}")

    def _check_scheduling_allowed(self) -> Tuple[bool, str]:
        """Check if scheduling is allowed based on usage/budget

        Returns:
            Tuple of (should_schedule: bool, status_message: str)
        """
        now = datetime.utcnow()

        if self.use_live_usage_check and self.usage_pause_until:
            if now < self.usage_pause_until:
                remaining = self.usage_pause_until - now
                message = (
                    f"Waiting for Pro plan reset at {self.usage_pause_until.strftime('%H:%M:%S')} "
                    f"({self._format_remaining(remaining)} remaining)"
                )
                return False, message
            # Pause window has expired; resume normal checks.
            self.usage_pause_until = None

        # Try live usage check first
        if self.use_live_usage_check and self.usage_checker:
            try:
                messages_used, messages_limit, reset_time = self.usage_checker.get_usage()
                usage_percent = (messages_used / messages_limit * 100) if messages_limit > 0 else 0

                if usage_percent >= self.pause_threshold_percent:
                    pause_base = reset_time if reset_time > now else now + self._usage_pause_default
                    pause_until = pause_base + self._usage_pause_grace
                    self.usage_pause_until = pause_until
                    remaining = pause_until - now
                    message = (
                        f"Pro plan usage at {usage_percent:.0f}% exceeds threshold {self.pause_threshold_percent:.0f}%; "
                        f"waiting for reset at {reset_time.strftime('%H:%M:%S')} "
                        f"(resume in {self._format_remaining(remaining)})"
                    )
                    return False, message
                else:
                    self.usage_pause_until = None
                    return True, f"Pro plan usage at {usage_percent:.0f}% - ready to schedule"

            except Exception as e:
                logger.debug(f"Live usage check failed, falling back to budget-based check: {e}")
                self.use_live_usage_check = False

        # Fall back to budget-based check
        estimated_cost = Decimal("0.50")
        is_budget_available = self.budget_manager.is_budget_available(estimated_cost=estimated_cost)

        if not is_budget_available:
            time_label = TimeOfDay.get_time_label()
            remaining = self.budget_manager.get_remaining_budget()

            if remaining <= Decimal("0"):
                message = (
                    f"Budget exhausted for {time_label} period "
                    f"(remaining: ${float(remaining):.4f}). Skipping task scheduling."
                )
            else:
                message = (
                    f"Remaining budget ${float(remaining):.4f} is below estimated task cost "
                    f"${float(estimated_cost):.2f} during {time_label} period; skipping task scheduling."
                )
            return False, message
        else:
            return True, f"Budget available (${float(self.budget_manager.get_remaining_budget()):.2f} remaining)"

    @staticmethod
    def _format_remaining(delta: timedelta) -> str:
        """Render a short human-readable remaining time string."""
        total_seconds = int(max(delta.total_seconds(), 0))
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        parts = []
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        if not parts and seconds:
            parts.append(f"{seconds}s")
        return " ".join(parts) if parts else "0s"

    def get_pause_remaining_seconds(self) -> Optional[float]:
        """Return remaining pause duration in seconds if scheduling is halted."""
        if not (self.use_live_usage_check and self.usage_pause_until):
            return None
        remaining = (self.usage_pause_until - datetime.utcnow()).total_seconds()
        return remaining if remaining > 0 else None

    def get_next_tasks(self) -> List[Task]:
        """Get next tasks to execute respecting concurrency, priorities, and budget"""
        self._init_current_window()

        # Check if we should schedule tasks using live usage or budget
        should_schedule, status_message = self._check_scheduling_allowed()

        if not should_schedule:
            now = datetime.utcnow()
            should_log = True
            if self._budget_exhausted_logged and self._last_budget_exhausted_log:
                should_log = (now - self._last_budget_exhausted_log).total_seconds() >= 60

            if should_log:
                logger.warning(status_message)
                self._last_budget_exhausted_log = now
                self._budget_exhausted_logged = True
            else:
                logger.debug(status_message)
            return []
        else:
            if self._budget_exhausted_logged:
                logger.info("Usage OK; resuming task scheduling.")
            self._budget_exhausted_logged = False
            self._last_budget_exhausted_log = None

        # Get in-progress tasks
        in_progress = self.task_queue.get_in_progress_tasks()
        available_slots = max(0, self.max_parallel_tasks - len(in_progress))

        if available_slots == 0:
            return []

        # Get pending tasks in priority order
        pending = self.task_queue.get_pending_tasks(limit=available_slots)

        # Log usage/budget info when scheduling
        if pending:
            if self.use_live_usage_check and self.usage_checker:
                try:
                    messages_used, messages_limit, _ = self.usage_checker.get_usage()
                    usage_percent = (messages_used / messages_limit * 100) if messages_limit > 0 else 0
                    logger.info(f"Scheduling {len(pending)} task(s) (Pro plan usage: {usage_percent:.0f}%)")
                except Exception:
                    # Fall back to budget info if usage check fails
                    budget_status = self.budget_manager.get_budget_status()
                    logger.info(
                        f"Scheduling {len(pending)} task(s) during {budget_status['time_period']} "
                        f"(Budget: ${budget_status['remaining_budget_usd']:.2f} remaining)"
                    )
            else:
                budget_status = self.budget_manager.get_budget_status()
                logger.info(
                    f"Scheduling {len(pending)} task(s) during {budget_status['time_period']} "
                    f"(Budget: ${budget_status['remaining_budget_usd']:.2f} remaining)"
                )

        return pending

    def schedule_task(
        self,
        description: str,
        priority: TaskPriority = TaskPriority.RANDOM,
        project_id: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> Task:
        """Schedule a new task"""
        task = self.task_queue.add_task(
            description=description,
            priority=priority,
            project_id=project_id,
            project_name=project_name,
        )

        # Log scheduling decision
        project_info = f" [Project: {project_name}]" if project_name else ""
        if priority == TaskPriority.SERIOUS:
            logger.info(f"🔴 Serious task scheduled: #{task.id}{project_info}")
        elif priority == TaskPriority.RANDOM:
            logger.info(f"🟡 Random thought scheduled: #{task.id}{project_info}")
        else:
            logger.info(f"🟢 Generated task scheduled: #{task.id}{project_info}")

        return task

    def record_task_usage(
        self,
        task_id: int,
        total_cost_usd: Optional[float] = None,
        duration_ms: Optional[int] = None,
        duration_api_ms: Optional[int] = None,
        num_turns: Optional[int] = None,
        project_id: Optional[str] = None,
    ):
        """Record API usage metrics for a completed task

        Args:
            task_id: Task ID
            total_cost_usd: Total cost in USD
            duration_ms: Total duration in milliseconds
            duration_api_ms: API call duration
            num_turns: Number of conversation turns
            project_id: Optional project ID for aggregation
        """
        session = self.task_queue.SessionLocal()
        try:
            usage = UsageMetric(
                task_id=task_id,
                total_cost_usd=str(total_cost_usd) if total_cost_usd is not None else None,
                duration_ms=duration_ms,
                duration_api_ms=duration_api_ms,
                num_turns=num_turns,
                project_id=project_id,
            )
            session.add(usage)
            session.commit()

            if total_cost_usd is not None:
                logger.info(
                    f"Recorded usage for task {task_id}: "
                    f"${total_cost_usd:.4f} ({num_turns} turns, {duration_ms}ms)"
                )
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to record usage for task {task_id}: {e}")
        finally:
            session.close()

    def get_credit_status(self) -> dict:
        """Get current credit usage status with budget information"""
        self._init_current_window()

        # Get queue status
        status = self.task_queue.get_queue_status()

        # Get budget status
        budget_status = self.budget_manager.get_budget_status()

        return {
            "current_window": {
                "start_time": self.current_window.start_time.isoformat(),
                "end_time": self.current_window.end_time.isoformat(),
                "time_remaining_minutes": self.current_window.time_remaining_minutes(),
                "tasks_executed": self.current_window.tasks_executed,
            },
            "budget": budget_status,
            "queue": status,
            "max_parallel": self.max_parallel_tasks,
        }

    def get_execution_slots_available(self) -> int:
        """Get available execution slots"""
        in_progress = len(self.task_queue.get_in_progress_tasks())
        return max(0, self.max_parallel_tasks - in_progress)

    def should_backfill_with_random_thoughts(self) -> bool:
        """Determine if we should fill idle time with random thoughts"""
        slots = self.get_execution_slots_available()

        if slots == 0:
            return False

        pending_serious = self.task_queue.task_queue.filter(
            status=TaskStatus.PENDING,
            priority=TaskPriority.SERIOUS,
        )

        # If no serious tasks, fill with random thoughts
        return len(pending_serious) == 0

    def estimate_task_priority_score(self, task: Task) -> float:
        """Calculate priority score for task sorting"""
        score = 0.0

        # Priority multiplier
        if task.priority == TaskPriority.SERIOUS:
            score += 1000
        elif task.priority == TaskPriority.RANDOM:
            score += 100
        elif task.priority == TaskPriority.GENERATED:
            score += 10

        # Age bonus (older tasks get higher score)
        age_minutes = (datetime.utcnow() - task.created_at).total_seconds() / 60
        score += age_minutes * 0.1

        # Retry penalty (don't keep retrying failed tasks)
        score -= task.attempt_count * 50

        return score

    def get_scheduled_tasks_info(self) -> List[dict]:
        """Get info about all scheduled tasks"""
        queue_status = self.task_queue.get_queue_status()

        return [
            {
                "status": "pending",
                "count": queue_status["pending"],
            },
            {
                "status": "in_progress",
                "count": queue_status["in_progress"],
            },
            {
                "status": "completed",
                "count": queue_status["completed"],
            },
        ]

    def log_task_execution(self, task_id: int):
        """Log task execution for credit tracking"""
        if self.current_window:
            self.current_window.tasks_executed += 1
            logger.info(
                f"Task {task_id} executed. Window: {self.current_window.tasks_executed} "
                f"tasks, {self.current_window.time_remaining_minutes()}m left"
            )

    def get_window_summary(self) -> str:
        """Get human-readable window summary"""
        self._init_current_window()
        return (
            f"Credit Window: {self.current_window.tasks_executed} tasks executed, "
            f"{self.current_window.time_remaining_minutes()} minutes remaining"
        )
