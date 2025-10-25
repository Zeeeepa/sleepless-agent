"""Smart task scheduler with usage tracking and time-based quotas"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from sleepless_agent.scheduling.time_utils import (
    current_period_start,
    get_time_label,
    is_nighttime,
)
from sleepless_agent.monitoring.logging import get_logger

from sleepless_agent.core.models import Task, TaskPriority, TaskStatus, UsageMetric
from sleepless_agent.core.queue import TaskQueue

logger = get_logger(__name__)


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
                    logger.warning(
                        "budget.parse_cost_failed",
                        cost=metric.total_cost_usd,
                        error=str(e),
                    )

        return total

    def get_today_usage(self) -> Decimal:
        """Get total usage for today (UTC midnight to now)"""
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        return self.get_usage_in_period(today_start)

    def get_current_time_period_usage(self) -> Decimal:
        """Get usage for current time period (night or day)"""
        period_start = current_period_start(datetime.utcnow())
        return self.get_usage_in_period(period_start)

    def get_current_quota(self) -> Decimal:
        """Get budget quota for current time period"""
        if is_nighttime():
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
        is_night = is_nighttime()
        time_label = get_time_label()

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
                logger.info(
                    "scheduler.usage_checker.ready",
                    command=usage_command,
                )
            except ImportError:
                logger.warning("scheduler.usage_checker.unavailable")
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
            logger.info(
                "scheduler.credit_window.new",
                window_start=self.current_window.start_time.isoformat(),
                window_end=self.current_window.end_time.isoformat(),
                minutes_left=self.current_window.time_remaining_minutes(),
            )

    def _check_scheduling_allowed(self) -> Tuple[bool, Dict[str, Any]]:
        """Check if scheduling is allowed based on usage/budget

        Returns:
            Tuple of (should_schedule: bool, context: dict)
        """
        now = datetime.utcnow()

        if self.use_live_usage_check and self.usage_pause_until:
            if now < self.usage_pause_until:
                remaining = self.usage_pause_until - now
                context = {
                    "event": "scheduler.pause.pending",
                    "reason": "usage_pause",
                    "resume_at": self.usage_pause_until.isoformat(),
                    "remaining_seconds": int(remaining.total_seconds()),
                    "detail": self._format_remaining(remaining),
                }
                return False, context
            # Pause window has expired; resume normal checks.
            self.usage_pause_until = None

        # Try live usage check first
        if self.use_live_usage_check and self.usage_checker:
            try:
                usage_percent, reset_time = self.usage_checker.get_usage()

                if usage_percent >= self.pause_threshold_percent:
                    pause_base = (
                        reset_time
                        if reset_time and reset_time > now
                        else now + self._usage_pause_default
                    )
                    pause_until = pause_base + self._usage_pause_grace
                    self.usage_pause_until = pause_until
                    remaining = pause_until - now
                    context = {
                        "event": "scheduler.pause.usage_threshold",
                        "reason": "usage_threshold",
                        "usage_percent": usage_percent,
                        "threshold_percent": self.pause_threshold_percent,
                        "resume_at": pause_until.isoformat(),
                        "reset_at": reset_time.isoformat() if reset_time else None,
                        "remaining_seconds": int(remaining.total_seconds()),
                        "detail": self._format_remaining(remaining),
                    }
                    return False, context
                else:
                    self.usage_pause_until = None
                    return True, {
                        "event": "scheduler.usage.ok",
                        "reason": "usage_ok",
                        "usage_percent": usage_percent,
                    }

            except Exception as e:
                logger.debug("scheduler.usage.check_failed", error=str(e))
                self.use_live_usage_check = False

        # Fall back to budget-based check
        estimated_cost = Decimal("0.50")
        is_budget_available = self.budget_manager.is_budget_available(estimated_cost=estimated_cost)

        if not is_budget_available:
            time_label = get_time_label()
            remaining = self.budget_manager.get_remaining_budget()

            if remaining <= Decimal("0"):
                context = {
                    "event": "scheduler.pause.budget_exhausted",
                    "reason": "budget_exhausted",
                    "time_period": time_label,
                    "remaining_budget_usd": float(remaining),
                }
            else:
                context = {
                    "event": "scheduler.pause.budget_low",
                    "reason": "budget_insufficient",
                    "time_period": time_label,
                    "remaining_budget_usd": float(remaining),
                    "estimated_task_cost_usd": float(estimated_cost),
                }
            return False, context
        else:
            return True, {
                "event": "scheduler.budget.ok",
                "reason": "budget_ok",
                "remaining_budget_usd": float(self.budget_manager.get_remaining_budget()),
            }

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
        should_schedule, context = self._check_scheduling_allowed()

        if not should_schedule:
            now = datetime.utcnow()
            event = context.pop("event", "scheduler.pause")
            reason = context.get("reason")
            should_log = True
            if reason in {"budget_exhausted", "budget_insufficient"}:
                if (
                    self._budget_exhausted_logged
                    and self._last_budget_exhausted_log
                    and (now - self._last_budget_exhausted_log).total_seconds() < 60
                ):
                    should_log = False
                if should_log:
                    self._budget_exhausted_logged = True
                    self._last_budget_exhausted_log = now
            if should_log:
                logger.warning(event, **context)
            else:
                logger.debug(event, **context)
            return []
        else:
            if self._budget_exhausted_logged:
                logger.info("scheduler.resume", **{k: v for k, v in context.items() if k != "event"})
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
            payload: Dict[str, Any] = {"tasks": len(pending)}
            if context.get("reason") in {"usage_ok", "usage_threshold"} and context.get("usage_percent") is not None:
                payload["usage_percent"] = context["usage_percent"]
            else:
                budget_status = self.budget_manager.get_budget_status()
                payload.update(
                    {
                        "time_period": budget_status["time_period"],
                        "remaining_budget_usd": budget_status["remaining_budget_usd"],
                    }
                )
            logger.info("scheduler.dispatch", **payload)

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
            logger.info(
                "scheduler.task.scheduled",
                task_id=task.id,
                priority="serious",
                project=project_name,
            )
        elif priority == TaskPriority.RANDOM:
            logger.info(
                "scheduler.task.scheduled",
                task_id=task.id,
                priority="random",
                project=project_name,
            )
        else:
            logger.info(
                "scheduler.task.scheduled",
                task_id=task.id,
                priority="generated",
                project=project_name,
            )

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
                    "scheduler.usage.recorded",
                    task_id=task_id,
                    cost_usd=total_cost_usd,
                    turns=num_turns,
                    duration_ms=duration_ms,
                )
        except Exception as e:
            session.rollback()
            logger.error(
                "scheduler.usage.record_failed",
                task_id=task_id,
                error=str(e),
            )
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
