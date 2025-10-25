"""Backward-compatibility re-exports for legacy imports."""

from sleepless_agent.tasks.models import Result, Task, TaskPriority, TaskStatus, init_db
from sleepless_agent.tasks.queue import TaskQueue
from sleepless_agent.scheduling.scheduler import SmartScheduler
from sleepless_agent.scheduling.auto_generator import AutoTaskGenerator

__all__ = [
    "Task",
    "Result",
    "TaskPriority",
    "TaskStatus",
    "init_db",
    "TaskQueue",
    "SmartScheduler",
    "AutoTaskGenerator",
]
