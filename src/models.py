"""SQLAlchemy models for task queue and results"""

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Column, DateTime, Enum as SQLEnum, Integer, String, Text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session

Base = declarative_base()


class TaskPriority(str, Enum):
    """Task priority levels"""
    RANDOM = "random"  # Low priority, experimental
    SERIOUS = "serious"  # High priority, needs completion


class TaskStatus(str, Enum):
    """Task status states"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Task(Base):
    """Task queue model"""
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    description = Column(Text, nullable=False)
    priority = Column(SQLEnum(TaskPriority), default=TaskPriority.RANDOM, nullable=False)
    status = Column(SQLEnum(TaskStatus), default=TaskStatus.PENDING, nullable=False)

    # Timing
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Execution details
    attempt_count = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)
    result_id = Column(Integer, nullable=True)  # Reference to Result

    # Metadata
    context = Column(Text, nullable=True)  # JSON with additional context
    assigned_to = Column(String(255), nullable=True)  # Slack user ID
    slack_thread_ts = Column(String(255), nullable=True)  # Slack thread timestamp for updates

    def __repr__(self):
        return f"<Task(id={self.id}, priority={self.priority}, status={self.status})>"


class Result(Base):
    """Stores results from completed tasks"""
    __tablename__ = "results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, nullable=False)

    # Results
    output = Column(Text, nullable=True)  # Main output/response
    files_modified = Column(Text, nullable=True)  # JSON list of modified files
    commands_executed = Column(Text, nullable=True)  # JSON list of executed commands

    # Git integration
    git_commit_sha = Column(String(40), nullable=True)
    git_pr_url = Column(String(512), nullable=True)
    git_branch = Column(String(255), nullable=True)

    # Workspace
    workspace_path = Column(String(512), nullable=True)  # Path to isolated task workspace

    # Metadata
    processing_time_seconds = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Result(id={self.id}, task_id={self.task_id})>"


def init_db(db_path: str) -> Session:
    """Initialize database and return session"""
    engine = create_engine(f"sqlite:///{db_path}", echo=False, future=True)
    Base.metadata.create_all(engine)
    return engine
