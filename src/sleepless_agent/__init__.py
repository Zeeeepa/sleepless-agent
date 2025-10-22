"""Sleepless Agent - 24/7 AI Assistant"""

from .core import Task, TaskPriority, TaskStatus, TaskQueue, SmartScheduler, init_db
from .interfaces import SlackBot
from .execution import ClaudeCodeExecutor
from .storage import ResultManager, GitManager
from .monitoring import HealthMonitor, PerformanceLogger

__version__ = "0.1.0"

__all__ = [
    "Task",
    "TaskPriority",
    "TaskStatus",
    "TaskQueue",
    "SmartScheduler",
    "init_db",
    "SlackBot",
    "ClaudeCodeExecutor",
    "ResultManager",
    "GitManager",
    "HealthMonitor",
    "PerformanceLogger",
]
