"""Sleepless Agent - 24/7 AI Assistant"""

from .core import Task, TaskPriority, TaskStatus, TaskQueue, SmartScheduler, init_db
from .interfaces import SlackBot, cli_main
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
    "cli_main",
    "ClaudeCodeExecutor",
    "ResultManager",
    "GitManager",
    "HealthMonitor",
    "PerformanceLogger",
]
