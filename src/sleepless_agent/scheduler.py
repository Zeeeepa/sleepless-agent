"""Smart task scheduler with credit tracking"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from sleepless_agent.models import Task, TaskPriority, TaskStatus
from sleepless_agent.task_queue import TaskQueue

logger = logging.getLogger(__name__)


class CreditWindow:
    """Tracks credit usage in 5-hour windows"""

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
    """Intelligent task scheduler with credit management"""

    def __init__(self, task_queue: TaskQueue, max_parallel_tasks: int = 3):
        """Initialize scheduler"""
        self.task_queue = task_queue
        self.max_parallel_tasks = max_parallel_tasks
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
        """Get next tasks to execute respecting concurrency and priorities"""
        self._init_current_window()

        # Get in-progress tasks
        in_progress = self.task_queue.get_in_progress_tasks()
        available_slots = max(0, self.max_parallel_tasks - len(in_progress))

        if available_slots == 0:
            return []

        # Get pending tasks in priority order
        pending = self.task_queue.get_pending_tasks(limit=available_slots)
        return pending

    def schedule_task(
        self,
        description: str,
        priority: TaskPriority = TaskPriority.RANDOM,
    ) -> Task:
        """Schedule a new task"""
        task = self.task_queue.add_task(description=description, priority=priority)

        # Log scheduling decision
        if priority == TaskPriority.SERIOUS:
            logger.info(f"🔴 Serious task scheduled: #{task.id}")
        else:
            logger.info(f"🟡 Random thought scheduled: #{task.id}")

        return task

    def get_credit_status(self) -> dict:
        """Get current credit usage status"""
        self._init_current_window()

        # Calculate estimated credit usage
        # Rough estimate: 100K input tokens = 1 credit, 1M output tokens = 1 credit
        status = self.task_queue.get_queue_status()

        return {
            "current_window": {
                "start_time": self.current_window.start_time.isoformat(),
                "end_time": self.current_window.end_time.isoformat(),
                "time_remaining_minutes": self.current_window.time_remaining_minutes(),
                "tasks_executed": self.current_window.tasks_executed,
            },
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
