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
    GENERATED = "generated"  # Auto-generated backlog filler


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
    priority = Column(
        SQLEnum(
            TaskPriority,
            native_enum=False,
            validate_strings=True,
            create_constraint=False,
        ),
        default=TaskPriority.RANDOM,
        nullable=False,
    )
    status = Column(SQLEnum(TaskStatus), default=TaskStatus.PENDING, nullable=False)

    # Timing
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)

    # Execution details
    attempt_count = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)
    result_id = Column(Integer, nullable=True)  # Reference to Result

    # Metadata
    context = Column(Text, nullable=True)  # JSON with additional context
    assigned_to = Column(String(255), nullable=True)  # Slack user ID
    slack_thread_ts = Column(String(255), nullable=True)  # Slack thread timestamp for updates

    # Project grouping - tasks with same project_id share workspace and context
    project_id = Column(String(255), nullable=True)  # Project identifier for context sharing
    project_name = Column(String(255), nullable=True)  # Human-readable project name

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


class UsageMetric(Base):
    """Track API usage and costs for budget management"""
    __tablename__ = "usage_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, nullable=False)

    # API usage details
    total_cost_usd = Column(Text, nullable=True)  # Stored as text to preserve precision
    duration_ms = Column(Integer, nullable=True)  # Total duration in milliseconds
    duration_api_ms = Column(Integer, nullable=True)  # API call duration
    num_turns = Column(Integer, nullable=True)  # Number of conversation turns

    # Timing
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Project tracking
    project_id = Column(String(255), nullable=True)  # Link to project for aggregation

    def __repr__(self):
        return f"<UsageMetric(id={self.id}, task_id={self.task_id}, cost=${self.total_cost_usd})>"


class TaskPool(Base):
    """Predefined pool of tasks for auto-generation"""
    __tablename__ = "task_pool"

    id = Column(Integer, primary_key=True, autoincrement=True)
    description = Column(Text, nullable=False)
    priority = Column(
        SQLEnum(
            TaskPriority,
            native_enum=False,
            validate_strings=True,
            create_constraint=False,
        ),
        default=TaskPriority.RANDOM,
        nullable=False,
    )
    category = Column(String(100), nullable=True)  # e.g., "refactor", "optimization", "testing"
    used = Column(Integer, default=0, nullable=False)  # How many times used
    project_id = Column(String(255), nullable=True)  # Optional project association
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<TaskPool(id={self.id}, priority={self.priority}, category={self.category})>"


class GenerationHistory(Base):
    """Track auto-generated tasks and their sources"""
    __tablename__ = "generation_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, nullable=False)  # Reference to created Task
    source = Column(String(50), nullable=False)  # "pool", "code", "ai", "backlog"
    usage_percent_at_generation = Column(Integer, nullable=False)  # Budget usage % when generated
    source_metadata = Column(Text, nullable=True)  # JSON with source-specific info
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<GenerationHistory(task_id={self.task_id}, source={self.source})>"


def init_db(db_path: str) -> Session:
    """Initialize database and return session"""
    engine = create_engine(f"sqlite:///{db_path}", echo=False, future=True)
    Base.metadata.create_all(engine)
    return engine
