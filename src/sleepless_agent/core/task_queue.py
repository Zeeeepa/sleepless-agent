"""Task queue management"""

import json
from datetime import datetime
from typing import List, Optional

from loguru import logger
from sqlalchemy import case, create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Task, TaskPriority, TaskStatus


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
        project_id: Optional[str] = None,
        project_name: Optional[str] = None,
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
                project_id=project_id,
                project_name=project_name,
            )
            session.add(task)
            session.commit()

            project_info = f" [Project: {project_name}]" if project_name else ""
            logger.info(f"Added task {task.id}: {description[:50]}...{project_info}")
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
            # Sort: serious first, random second, generated last
            priority_order = case(
                (Task.priority == TaskPriority.SERIOUS.value, 0),
                (Task.priority == TaskPriority.RANDOM.value, 1),
                else_=2,
            )
            tasks = (
                session.query(Task)
                .filter(Task.status == TaskStatus.PENDING)
                .order_by(priority_order, Task.created_at)
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
        """Cancel pending task (soft delete)"""
        session = self.SessionLocal()
        try:
            task = session.query(Task).filter(Task.id == task_id).first()
            if task and task.status == TaskStatus.PENDING:
                task.status = TaskStatus.CANCELLED
                task.deleted_at = datetime.utcnow()
                session.commit()
                logger.info(f"Task {task_id} cancelled and moved to trash")
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

    def get_projects(self) -> List[dict]:
        """Get all projects with task counts and status"""
        session = self.SessionLocal()
        try:
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
        finally:
            session.close()

    def get_project_by_id(self, project_id: str) -> Optional[dict]:
        """Get project info by ID"""
        session = self.SessionLocal()
        try:
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
        finally:
            session.close()

    def get_project_tasks(self, project_id: str) -> List[Task]:
        """Get all tasks for a project"""
        session = self.SessionLocal()
        try:
            tasks = session.query(Task).filter(Task.project_id == project_id).order_by(
                Task.created_at.desc()
            ).all()
            return tasks
        finally:
            session.close()

    def delete_project(self, project_id: str) -> int:
        """Soft delete all tasks in a project (mark as CANCELLED). Returns count of affected tasks."""
        session = self.SessionLocal()
        try:
            tasks = session.query(Task).filter(Task.project_id == project_id).all()
            count = 0
            for task in tasks:
                if task.status == TaskStatus.PENDING:
                    task.status = TaskStatus.CANCELLED
                    task.deleted_at = datetime.utcnow()
                    count += 1
            session.commit()
            logger.info(f"Soft deleted project {project_id}: {count} tasks moved to trash")
            return count
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to delete project {project_id}: {e}")
            raise
        finally:
            session.close()
