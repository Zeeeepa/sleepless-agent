"""Manage predefined task pool for auto-generation"""

from typing import List, Optional

from loguru import logger
from sqlalchemy.orm import Session

from sleepless_agent.core.models import TaskPool, TaskPriority


class TaskPoolManager:
    """Manage predefined pool of tasks for auto-generation"""

    def __init__(self, db_session: Session):
        """Initialize task pool manager"""
        self.session = db_session

    def add_task(
        self,
        description: str,
        priority: TaskPriority = TaskPriority.RANDOM,
        category: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> TaskPool:
        """Add a task to the pool"""
        task = TaskPool(
            description=description,
            priority=priority,
            category=category,
            project_id=project_id,
            used=0,
        )
        self.session.add(task)
        self.session.commit()
        logger.info(f"Added task to pool: {description[:60]}")
        return task

    def get_next_task(self) -> Optional[str]:
        """Get next task from pool (least-used tasks first)"""
        task = self.session.query(TaskPool).order_by(TaskPool.used, TaskPool.id).first()

        if not task:
            return None

        # Increment usage counter
        task.used += 1
        self.session.commit()

        return task.description

    def get_unused_count(self) -> int:
        """Get count of tasks with usage == 0"""
        return self.session.query(TaskPool).filter(TaskPool.used == 0).count()

    def get_total_count(self) -> int:
        """Get total count of tasks in pool"""
        return self.session.query(TaskPool).count()

    def get_all_tasks(self, limit: int = 50) -> List[dict]:
        """Get all tasks in pool"""
        tasks = self.session.query(TaskPool).limit(limit).all()
        return [
            {
                "id": t.id,
                "description": t.description,
                "priority": t.priority.value,
                "category": t.category,
                "used": t.used,
                "project_id": t.project_id,
            }
            for t in tasks
        ]

    def remove_task(self, task_id: int) -> bool:
        """Remove task from pool"""
        task = self.session.query(TaskPool).filter(TaskPool.id == task_id).first()
        if task:
            self.session.delete(task)
            self.session.commit()
            logger.info(f"Removed task {task_id} from pool")
            return True
        return False

    def get_pool_stats(self) -> dict:
        """Get statistics about the task pool"""
        total = self.get_total_count()
        unused = self.get_unused_count()

        # Get stats by category
        tasks = self.session.query(TaskPool).all()
        by_category = {}
        by_priority = {}

        for task in tasks:
            cat = task.category or "uncategorized"
            by_category[cat] = by_category.get(cat, 0) + 1

            pri = task.priority.value
            by_priority[pri] = by_priority.get(pri, 0) + 1

        return {
            "total_tasks": total,
            "unused_tasks": unused,
            "used_ratio": f"{(total - unused) / total * 100:.1f}%" if total > 0 else "0%",
            "by_category": by_category,
            "by_priority": by_priority,
        }
