"""Smart task scheduler with usage tracking and time-based quotas"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional

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
    ):
        """Initialize scheduler

        Args:
            task_queue: Task queue instance
            max_parallel_tasks: Maximum parallel tasks (default: 3)
            daily_budget_usd: Daily budget in USD (default: $10)
            night_quota_percent: Percentage for night usage (default: 90%)
        """
        self.task_queue = task_queue
        self.max_parallel_tasks = max_parallel_tasks

        # Budget management with time-based allocation
        session = self.task_queue.SessionLocal()
        self.budget_manager = BudgetManager(
            session=session,
            daily_budget_usd=daily_budget_usd,
            night_quota_percent=night_quota_percent,
        )

        # Legacy credit window support
        self.active_windows: List[CreditWindow] = []
        self.current_window: Optional[CreditWindow] = None
        self._init_current_window()

    def _init_current_window(self):
        """Initialize current credit window"""
        now = datetime.utcnow()

        # Check if we need a new window
        if not self.current_window or not self.current_window.is_active():
            self.current_window = CreditWindow(start_time=now)
            self.active_windows.append(self.current_window)
            logger.info(f"New credit window started: {self.current_window}")

    def get_next_tasks(self) -> List[Task]:
        """Get next tasks to execute respecting concurrency, priorities, and budget"""
        self._init_current_window()

        # Check if budget is available
        if not self.budget_manager.is_budget_available():
            time_label = TimeOfDay.get_time_label()
            remaining = self.budget_manager.get_remaining_budget()
            logger.warning(
                f"Budget exhausted for {time_label} period "
                f"(remaining: ${remaining:.4f}). Skipping task scheduling."
            )
            return []

        # Get in-progress tasks
        in_progress = self.task_queue.get_in_progress_tasks()
        available_slots = max(0, self.max_parallel_tasks - len(in_progress))

        if available_slots == 0:
            return []

        # Get pending tasks in priority order
        pending = self.task_queue.get_pending_tasks(limit=available_slots)

        # Log budget info when scheduling
        if pending:
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
        else:
            logger.info(f"🟡 Random thought scheduled: #{task.id}{project_info}")

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
        else:
            score += 100

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
