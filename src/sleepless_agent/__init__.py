"""Sleepless Agent - 24/7 AI Assistant"""

from sleepless_agent.interfaces import SlackBot, cli_main
from sleepless_agent.monitoring import HealthMonitor, PerformanceLogger
from sleepless_agent.storage.results import ResultManager
from sleepless_agent.core.daemon import SleeplessAgent
from sleepless_agent.scheduling.auto_generator import AutoTaskGenerator
from sleepless_agent.scheduling.scheduler import SmartScheduler
from sleepless_agent.core.models import (
    Result,
    Task,
    TaskPriority,
    TaskStatus,
    init_db,
)
from sleepless_agent.core.queue import TaskQueue
from sleepless_agent.core.executor import ClaudeCodeExecutor
from sleepless_agent.storage.git import GitManager

__version__ = "0.1.2"

__all__ = [
    "SleeplessAgent",
    "Task",
    "TaskPriority",
    "TaskStatus",
    "TaskQueue",
    "SmartScheduler",
    "AutoTaskGenerator",
    "Result",
    "init_db",
    "SlackBot",
    "cli_main",
    "ClaudeCodeExecutor",
    "ResultManager",
    "GitManager",
    "HealthMonitor",
    "PerformanceLogger",
]
