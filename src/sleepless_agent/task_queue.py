"""Task queue management"""

import json
import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from sleepless_agent.models import Task, TaskPriority, TaskStatus

logger = logging.getLogger(__name__)


class TaskQueue:
    """Task queue manager"""

    def __init__(self, db_path: str):
        """Initialize task queue with database"""
        self.engine = create_engine(f"sqlite:///{db_path}", echo=False, future=True)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)

    def add_task(
        self,
        description: str,
        priority: TaskPriority = TaskPriority.RANDOM,
        context: Optional[dict] = None,
        slack_user_id: Optional[str] = None,
        slack_thread_ts: Optional[str] = None,
    ) -> Task:
        """Add new task to queue"""
        session = self.SessionLocal()
        try:
            task = Task(
                description=description,
                priority=priority,
                context=json.dumps(context) if context else None,
                assigned_to=slack_user_id,
                slack_thread_ts=slack_thread_ts,
            )
            session.add(task)
            session.commit()
            logger.info(f"Added task {task.id}: {description[:50]}...")
            return task
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to add task: {e}")
            raise
        finally:
            session.close()

    def get_task(self, task_id: int) -> Optional[Task]:
        """Get task by ID"""
        session = self.SessionLocal()
        try:
            task = session.query(Task).filter(Task.id == task_id).first()
            return task
        finally:
            session.close()

    def get_pending_tasks(self, limit: int = 10) -> List[Task]:
        """Get pending tasks sorted by priority"""
        session = self.SessionLocal()
        try:
            # Sort: serious first, then by created_at
            tasks = (
                session.query(Task)
                .filter(Task.status == TaskStatus.PENDING)
                .order_by(
                    Task.priority == TaskPriority.SERIOUS.value,  # Serious first
                    Task.created_at,
                )
                .limit(limit)
                .all()
            )
            return tasks
        finally:
            session.close()

    def get_in_progress_tasks(self) -> List[Task]:
        """Get all in-progress tasks"""
        session = self.SessionLocal()
        try:
            tasks = session.query(Task).filter(Task.status == TaskStatus.IN_PROGRESS).all()
            return tasks
        finally:
            session.close()

    def mark_in_progress(self, task_id: int) -> Task:
        """Mark task as in progress"""
        session = self.SessionLocal()
        try:
            task = session.query(Task).filter(Task.id == task_id).first()
            if task:
                task.status = TaskStatus.IN_PROGRESS
                task.started_at = datetime.utcnow()
                task.attempt_count += 1
                session.commit()
                logger.info(f"Task {task_id} marked as in_progress")
            return task
        finally:
            session.close()

    def mark_completed(self, task_id: int, result_id: Optional[int] = None) -> Task:
        """Mark task as completed"""
        session = self.SessionLocal()
        try:
            task = session.query(Task).filter(Task.id == task_id).first()
            if task:
                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.utcnow()
                task.result_id = result_id
                session.commit()
                logger.info(f"Task {task_id} marked as completed")
            return task
        finally:
            session.close()

    def mark_failed(self, task_id: int, error_message: str) -> Task:
        """Mark task as failed"""
        session = self.SessionLocal()
        try:
            task = session.query(Task).filter(Task.id == task_id).first()
            if task:
                task.status = TaskStatus.FAILED
                task.error_message = error_message
                session.commit()
                logger.error(f"Task {task_id} marked as failed: {error_message}")
            return task
        finally:
            session.close()

    def cancel_task(self, task_id: int) -> Optional[Task]:
        """Cancel pending task"""
        session = self.SessionLocal()
        try:
            task = session.query(Task).filter(Task.id == task_id).first()
            if task and task.status == TaskStatus.PENDING:
                task.status = TaskStatus.CANCELLED
                session.commit()
                logger.info(f"Task {task_id} cancelled")
            return task
        finally:
            session.close()

    def update_priority(self, task_id: int, priority: TaskPriority) -> Optional[Task]:
        """Update task priority"""
        session = self.SessionLocal()
        try:
            task = session.query(Task).filter(Task.id == task_id).first()
            if task:
                task.priority = priority
                session.commit()
                logger.info(f"Task {task_id} priority updated to {priority}")
            return task
        finally:
            session.close()

    def get_queue_status(self) -> dict:
        """Get overall queue status"""
        session = self.SessionLocal()
        try:
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
        finally:
            session.close()

    def get_task_context(self, task_id: int) -> Optional[dict]:
        """Get task context as dict"""
        task = self.get_task(task_id)
        if task and task.context:
            return json.loads(task.context)
        return None
