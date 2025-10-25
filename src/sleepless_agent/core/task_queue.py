"""Task queue management"""

import json
from datetime import datetime, timedelta
from typing import Callable, List, Optional, TypeVar

from loguru import logger
from sqlalchemy import case, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.exc import OperationalError

from .models import Task, TaskPriority, TaskStatus

T = TypeVar("T")


def with_session(read_only: bool = True):
    """Decorator for database operations with automatic session management.

    This decorator eliminates code duplication by handling session lifecycle,
    error handling, and cleanup automatically. It injects a session as the
    first parameter after self to decorated methods.

    Args:
        read_only: If True, only closes session on error. If False, commits on
                   success and rolls back on error.

    Example:
        @with_session(read_only=True)
        def get_task(self, session: Session, task_id: int) -> Optional[Task]:
            return session.query(Task).filter(Task.id == task_id).first()

    Features:
        - Automatic session creation from self.SessionLocal
        - Proper commit/rollback based on read_only flag
        - Guaranteed session cleanup via finally block
        - Consistent error logging
        - Preserves original function metadata via functools.wraps
    """
    from functools import wraps

    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            session = self.SessionLocal()
            try:
                result = func(self, session, *args, **kwargs)
                if not read_only:
                    session.commit()
                return result
            except Exception as e:
                if not read_only:
                    session.rollback()
                logger.error(f"Error in {func.__name__}: {e}")
                raise
            finally:
                session.close()
        return wrapper
    return decorator


def with_session_retry(max_retries: int = 2):
    """Decorator for write operations with retry logic for SQLite concurrency issues.

    This decorator combines session management with intelligent retry logic for
    handling SQLite-specific operational errors (read-only state, database locked).
    It's designed specifically for write operations that may fail due to transient
    SQLite concurrency issues.

    Args:
        max_retries: Maximum number of retry attempts (default: 2)

    Example:
        @with_session_retry(max_retries=2)
        def mark_completed(self, session: Session, task_id: int) -> Task:
            task = session.query(Task).filter(Task.id == task_id).first()
            if task:
                task.status = TaskStatus.COMPLETED
            return task

    Features:
        - Automatic session creation and cleanup
        - Intelligent retry on OperationalError (read-only/locked states)
        - Engine reset between retries for recovery
        - Automatic commit on success, rollback on failure
        - Detailed error logging with context
        - Thread-safe operation

    Retry Logic:
        - On OperationalError with specific messages, resets engine and retries
        - Only resets on first attempt to avoid infinite loops
        - Raises original exception if all retries exhausted
    """
    from functools import wraps

    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            for attempt in range(max_retries):
                session = self.SessionLocal()
                try:
                    result = func(self, session, *args, **kwargs)
                    session.commit()
                    return result
                except OperationalError as exc:
                    session.rollback()
                    if self._should_reset_on_error(exc) and attempt < max_retries - 1:
                        logger.warning(
                            f"SQLite operation failed in {func.__name__}; "
                            f"resetting connection (attempt {attempt + 1}/{max_retries})"
                        )
                        session.close()
                        session = None
                        self._reset_engine()
                        continue
                    logger.error(f"OperationalError in {func.__name__} after {attempt + 1} attempts: {exc}")
                    raise
                except Exception as e:
                    session.rollback()
                    logger.error(f"Error in {func.__name__}: {e}")
                    raise
                finally:
                    if session is not None:
                        session.close()
            raise RuntimeError(f"Failed to execute {func.__name__} after {max_retries} retries")
        return wrapper
    return decorator


class TaskQueue:
    """Task queue manager"""

    def __init__(self, db_path: str):
        """Initialize task queue with database"""
        self.db_path = db_path
        self._create_engine()

    def _create_engine(self):
        """Create SQLAlchemy engine using SQLite's thread-local connection pool."""
        self.engine = create_engine(f"sqlite:///{self.db_path}", echo=False, future=True)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)

    def _reset_engine(self):
        self.engine.dispose(close=True)
        self._create_engine()

    def get_pool_status(self) -> dict:
        """Get connection pool status for monitoring.

        Returns:
            Dictionary with pool statistics including size and connections in use.
        """
        pool = self.engine.pool
        return {
            "pool_class": pool.__class__.__name__,
            "size": getattr(pool, "size", lambda: "N/A")() if callable(getattr(pool, "size", None)) else "N/A",
            "checked_in": getattr(pool, "checkedin", lambda: 0)() if callable(getattr(pool, "checkedin", None)) else 0,
            "checked_out": getattr(pool, "checkedout", lambda: 0)() if callable(getattr(pool, "checkedout", None)) else 0,
            "overflow": getattr(pool, "overflow", lambda: 0)() if callable(getattr(pool, "overflow", None)) else 0,
        }

    @staticmethod
    def _should_reset_on_error(exc: OperationalError) -> bool:
        """Check if an OperationalError warrants a connection reset."""
        message = str(exc).lower()
        return "readonly" in message or ("sqlite" in message and "locked" in message)

    @with_session_retry(max_retries=2)
    def add_task(
        self,
        session: Session,
        description: str,
        priority: TaskPriority = TaskPriority.RANDOM,
        context: Optional[dict] = None,
        slack_user_id: Optional[str] = None,
        slack_thread_ts: Optional[str] = None,
        project_id: Optional[str] = None,
        project_name: Optional[str] = None,
    ) -> Task:
        """Add new task to queue"""
        task = Task(
            description=description,
            priority=priority,
            context=json.dumps(context) if context else None,
            assigned_to=slack_user_id,
            slack_thread_ts=slack_thread_ts,
            project_id=project_id,
            project_name=project_name,
        )
        session.add(task)
        session.flush()  # Flush to get task.id before commit

        project_info = f" [Project: {project_name}]" if project_name else ""
        logger.info(f"Added task {task.id}: {description[:50]}...{project_info}")
        return task

    @with_session(read_only=True)
    def get_task(self, session: Session, task_id: int) -> Optional[Task]:
        """Get task by ID"""
        return session.query(Task).filter(Task.id == task_id).first()

    @with_session(read_only=True)
    def get_pending_tasks(self, session: Session, limit: int = 10) -> List[Task]:
        """Get pending tasks sorted by priority"""
        # Sort: serious first, random second, generated last
        priority_order = case(
            (Task.priority == TaskPriority.SERIOUS.value, 0),
            (Task.priority == TaskPriority.RANDOM.value, 1),
            else_=2,
        )
        return (
            session.query(Task)
            .filter(Task.status == TaskStatus.PENDING)
            .order_by(priority_order, Task.created_at)
            .limit(limit)
            .all()
        )

    @with_session(read_only=True)
    def get_in_progress_tasks(self, session: Session) -> List[Task]:
        """Get all in-progress tasks"""
        return session.query(Task).filter(Task.status == TaskStatus.IN_PROGRESS).all()

    @with_session_retry(max_retries=2)
    def mark_in_progress(self, session: Session, task_id: int) -> Task:
        """Mark task as in progress"""
        task = session.query(Task).filter(Task.id == task_id).first()
        if task:
            task.status = TaskStatus.IN_PROGRESS
            task.started_at = datetime.utcnow()
            task.attempt_count += 1
            logger.info(f"Task {task_id} marked as in_progress")
        return task

    @with_session_retry(max_retries=2)
    def mark_completed(self, session: Session, task_id: int, result_id: Optional[int] = None) -> Task:
        """Mark task as completed"""
        task = session.query(Task).filter(Task.id == task_id).first()
        if task:
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.utcnow()
            task.result_id = result_id
            logger.info(f"Task {task_id} marked as completed")
        return task

    @with_session_retry(max_retries=2)
    def mark_failed(self, session: Session, task_id: int, error_message: str) -> Task:
        """Mark task as failed"""
        task = session.query(Task).filter(Task.id == task_id).first()
        if task:
            task.status = TaskStatus.FAILED
            task.error_message = error_message
            if not task.completed_at:
                task.completed_at = datetime.utcnow()
            logger.error(f"Task {task_id} marked as failed: {error_message}")
        return task

    @with_session_retry(max_retries=2)
    def cancel_task(self, session: Session, task_id: int) -> Optional[Task]:
        """Cancel pending task (soft delete)"""
        task = session.query(Task).filter(Task.id == task_id).first()
        if task and task.status == TaskStatus.PENDING:
            task.status = TaskStatus.CANCELLED
            task.deleted_at = datetime.utcnow()
            logger.info(f"Task {task_id} cancelled and moved to trash")
        return task

    @with_session_retry(max_retries=2)
    def update_priority(self, session: Session, task_id: int, priority: TaskPriority) -> Optional[Task]:
        """Update task priority"""
        task = session.query(Task).filter(Task.id == task_id).first()
        if task:
            task.priority = priority
            logger.info(f"Task {task_id} priority updated to {priority}")
        return task

    @with_session(read_only=True)
    def get_queue_status(self, session: Session) -> dict:
        """Get overall queue status"""
        total = session.query(Task).count()
        pending = session.query(Task).filter(Task.status == TaskStatus.PENDING).count()
        in_progress = session.query(Task).filter(Task.status == TaskStatus.IN_PROGRESS).count()
        completed = session.query(Task).filter(Task.status == TaskStatus.COMPLETED).count()
        failed = session.query(Task).filter(Task.status == TaskStatus.FAILED).count()

        return {
            "total": total,
            "pending": pending,
            "in_progress": in_progress,
            "completed": completed,
            "failed": failed,
        }

    def get_task_context(self, task_id: int) -> Optional[dict]:
        """Get task context as dict"""
        task = self.get_task(task_id)
        if task and task.context:
            return json.loads(task.context)
        return None

    @with_session(read_only=True)
    def get_projects(self, session: Session) -> List[dict]:
        """Get all projects with task counts and status"""
        projects = session.query(Task.project_id, Task.project_name).filter(
            Task.project_id.isnot(None)
        ).distinct().all()

        result = []
        for project_id, project_name in projects:
            if project_id is None:
                continue

            tasks = session.query(Task).filter(Task.project_id == project_id).all()
            pending = sum(1 for t in tasks if t.status == TaskStatus.PENDING)
            in_progress = sum(1 for t in tasks if t.status == TaskStatus.IN_PROGRESS)
            completed = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)

            result.append({
                'project_id': project_id,
                'project_name': project_name or project_id,
                'total_tasks': len(tasks),
                'pending': pending,
                'in_progress': in_progress,
                'completed': completed,
            })

        return sorted(result, key=lambda x: x['project_id'])

    @with_session_retry(max_retries=2)
    def timeout_expired_tasks(self, session: Session, max_age_seconds: int) -> List[Task]:
        """Mark in-progress tasks that exceed the timeout as failed and return them."""
        if max_age_seconds <= 0:
            return []

        cutoff = datetime.utcnow() - timedelta(seconds=max_age_seconds)
        tasks = (
            session.query(Task)
            .filter(
                Task.status == TaskStatus.IN_PROGRESS,
                Task.started_at.isnot(None),
                Task.started_at < cutoff,
            )
            .all()
        )

        if not tasks:
            return []

        now = datetime.utcnow()
        for task in tasks:
            task.status = TaskStatus.FAILED
            task.completed_at = now
            task.error_message = (
                f"Timed out after exceeding {max_age_seconds // 60} minute limit."
            )

        logger.warning(
            f"Timed out tasks: {[task.id for task in tasks]} (>{max_age_seconds}s)"
        )
        return tasks

    @with_session(read_only=True)
    def get_project_by_id(self, session: Session, project_id: str) -> Optional[dict]:
        """Get project info by ID"""
        tasks = session.query(Task).filter(Task.project_id == project_id).all()
        if not tasks:
            return None

        first_task = tasks[0]
        pending = sum(1 for t in tasks if t.status == TaskStatus.PENDING)
        in_progress = sum(1 for t in tasks if t.status == TaskStatus.IN_PROGRESS)
        completed = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
        failed = sum(1 for t in tasks if t.status == TaskStatus.FAILED)

        return {
            'project_id': project_id,
            'project_name': first_task.project_name or project_id,
            'total_tasks': len(tasks),
            'pending': pending,
            'in_progress': in_progress,
            'completed': completed,
            'failed': failed,
            'created_at': min(t.created_at for t in tasks),
            'tasks': [
                {
                    'id': t.id,
                    'description': t.description[:50],
                    'status': t.status.value,
                    'priority': t.priority.value,
                    'created_at': t.created_at.isoformat(),
                }
                for t in sorted(tasks, key=lambda x: x.created_at, reverse=True)[:5]
            ]
        }

    @with_session(read_only=True)
    def get_project_tasks(self, session: Session, project_id: str) -> List[Task]:
        """Get all tasks for a project"""
        return session.query(Task).filter(Task.project_id == project_id).order_by(
            Task.created_at.desc()
        ).all()

    @with_session(read_only=True)
    def get_recent_tasks(self, session: Session, limit: int = 10) -> List[Task]:
        """Get the most recent tasks across all projects."""
        return (
            session.query(Task)
            .order_by(Task.created_at.desc())
            .limit(limit)
            .all()
        )

    @with_session(read_only=True)
    def get_failed_tasks(self, session: Session, limit: int = 10) -> List[Task]:
        """Get the most recent failed tasks."""
        return (
            session.query(Task)
            .filter(Task.status == TaskStatus.FAILED)
            .order_by(Task.created_at.desc())
            .limit(limit)
            .all()
        )

    @with_session_retry(max_retries=2)
    def delete_project(self, session: Session, project_id: str) -> int:
        """Soft delete all tasks in a project (mark as CANCELLED). Returns count of affected tasks."""
        tasks = session.query(Task).filter(Task.project_id == project_id).all()
        count = 0
        for task in tasks:
            if task.status == TaskStatus.PENDING:
                task.status = TaskStatus.CANCELLED
                task.deleted_at = datetime.utcnow()
                count += 1
        logger.info(f"Soft deleted project {project_id}: {count} tasks moved to trash")
        return count
