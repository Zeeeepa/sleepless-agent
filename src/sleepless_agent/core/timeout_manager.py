from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING

from sleepless_agent.monitoring.logging import get_logger

from sleepless_agent.core.queue import TaskQueue
from sleepless_agent.monitoring.monitor import HealthMonitor, PerformanceLogger
from sleepless_agent.monitoring.report_generator import ReportGenerator, TaskMetrics
from sleepless_agent.core.executor import ClaudeCodeExecutor

if TYPE_CHECKING:
    from sleepless_agent.interfaces.bot import SlackBot

logger = get_logger(__name__)


class TaskTimeoutManager:
    """Handle task timeout enforcement and related reporting."""

    def __init__(
        self,
        *,
        config,
        task_queue: TaskQueue,
        claude: ClaudeCodeExecutor,
        monitor: HealthMonitor,
        perf_logger: PerformanceLogger,
        report_generator: ReportGenerator,
        bot: Optional["SlackBot"],
        live_status_tracker,
    ):
        self.config = config
        self.task_queue = task_queue
        self.claude = claude
        self.monitor = monitor
        self.perf_logger = perf_logger
        self.report_generator = report_generator
        self.bot = bot
        self.live_status_tracker = live_status_tracker

    def enforce(self) -> None:
        timeout_seconds = self.config.agent.task_timeout_seconds
        if timeout_seconds <= 0:
            return

        timed_out_tasks = self.task_queue.timeout_expired_tasks(timeout_seconds)
        if not timed_out_tasks:
            return

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for task in timed_out_tasks:
            elapsed_seconds = self._compute_elapsed(task, now, timeout_seconds)
            timeout_message = task.error_message or f"Timed out after {elapsed_seconds // 60} minutes."

            cleanup_note = "workspace left in place"
            try:
                cleaned = self.claude.cleanup_workspace(task.id, force=False)
                if cleaned:
                    cleanup_note = "workspace cleaned"
            except Exception as exc:
                cleanup_note = "workspace cleanup failed"
                logger.debug(f"Failed to cleanup workspace for task {task.id}: {exc}")

            logger.warning(f"Task {task.id} timed out after {elapsed_seconds}s ({cleanup_note})")

            self._log_timeout_metrics(task, elapsed_seconds, timeout_message)
            self._notify_timeout(task, elapsed_seconds, timeout_message)

    def _compute_elapsed(self, task, now: datetime, timeout_seconds: int) -> int:
        started_at = task.started_at or now
        completed_at = task.completed_at or now
        elapsed_seconds = int((completed_at - started_at).total_seconds())
        return max(elapsed_seconds, timeout_seconds)

    def _log_timeout_metrics(self, task, elapsed_seconds: int, timeout_message: str) -> None:
        try:
            self.monitor.record_task_completion(elapsed_seconds, success=False)
        except Exception as exc:
            logger.debug(f"Failed to record timeout in health monitor for task {task.id}: {exc}")

        try:
            self.perf_logger.log_task_execution(
                task_id=task.id,
                description=task.description,
                priority=task.priority.value if task.priority else "unknown",
                duration_seconds=elapsed_seconds,
                success=False,
            )
        except Exception as exc:
            logger.debug(f"Failed to log timeout metrics for task {task.id}: {exc}")

        try:
            task_metrics = TaskMetrics(
                task_id=task.id,
                description=task.description,
                priority=task.priority.value if task.priority else "unknown",
                status="failed",
                duration_seconds=elapsed_seconds,
                files_modified=0,
                commands_executed=0,
                error_message=timeout_message,
            )
            self.report_generator.append_task_completion(task_metrics, project_id=task.project_id)
        except Exception as exc:
            logger.debug(f"Failed to append timeout to report for task {task.id}: {exc}")

    def _notify_timeout(self, task, elapsed_seconds: int, timeout_message: str) -> None:
        if task.assigned_to and self.bot:
            try:
                minutes = max(1, elapsed_seconds // 60)
                self.bot.send_message(
                    task.assigned_to,
                    f"⏱️ Task #{task.id} timed out after {minutes} minute(s). "
                    "It has been marked as failed.",
                )
            except Exception as exc:
                logger.debug(f"Failed to send timeout notification for task {task.id}: {exc}")

        if self.live_status_tracker:
            try:
                self.live_status_tracker.clear(task.id)
            except Exception as exc:
                logger.debug(f"Failed to clear live status for timed-out task {task.id}: {exc}")
