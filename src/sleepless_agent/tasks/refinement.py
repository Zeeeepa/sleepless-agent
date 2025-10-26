"""Utilities for generating refinement follow-up tasks."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence

from sleepless_agent.monitoring.logging import get_logger
logger = get_logger(__name__)

from sqlalchemy.orm import Session

from sleepless_agent.core.models import GenerationHistory, Task, TaskPriority, TaskStatus
from sleepless_agent.core.queue import TaskQueue


REFINEMENT_CONTEXT_KEY = "refinement_parent_task_id"


def _normalize_text_list(items: Sequence[str]) -> list[str]:
    """Clean and normalize bullet-style strings."""
    normalized: list[str] = []
    for item in items or []:
        text = item.strip()
        text = text.strip("- *[]•✓❌")
        if text:
            normalized.append(text)
    return normalized


def build_refinement_description(
    *,
    source_task: Task,
    project_name: Optional[str],
    recommendations: Sequence[str] | None,
    outstanding_items: Sequence[str] | None,
) -> str:
    """Create a human-readable refinement task description."""
    recommendations = _normalize_text_list(recommendations or [])
    outstanding_items = _normalize_text_list(outstanding_items or [])

    base_label = project_name or "project"
    description = f"Refine {base_label}: {source_task.description[:140]}"

    if recommendations:
        description = f"Refine {base_label}: {recommendations[0]}"
    elif outstanding_items:
        description = f"Refine {base_label}: {outstanding_items[0]}"

    return description


def ensure_refinement_task(
    *,
    task_queue: TaskQueue,
    session: Session,
    source_task: Task,
    project_name: Optional[str],
    recommendations: Sequence[str] | None = None,
    outstanding_items: Sequence[str] | None = None,
) -> Optional[Task]:
    """Create a refinement task if one does not already exist for the source task."""
    parent_id = source_task.id

    existing = (
        session.query(Task)
        .filter(
            Task.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS]),
            Task.context.isnot(None),
        )
        .all()
    )

    for candidate in existing:
        try:
            context = json.loads(candidate.context)
        except (TypeError, json.JSONDecodeError):
            continue
        if context.get(REFINEMENT_CONTEXT_KEY) == parent_id:
            logger.debug(f"Refinement task already exists for task {parent_id}")
            return None

    description = build_refinement_description(
        source_task=source_task,
        project_name=project_name,
        recommendations=recommendations,
        outstanding_items=outstanding_items,
    )

    context = {
        "generated_by": "refinement",
        REFINEMENT_CONTEXT_KEY: parent_id,
        "generated_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
    }

    refinement_task = task_queue.add_task(
        description=description,
        priority=TaskPriority.SERIOUS,
        context=context,
        project_id=source_task.project_id,
        project_name=project_name,
    )

    history = GenerationHistory(
        task_id=refinement_task.id,
        source="refinement",
        usage_percent_at_generation=0,
        source_metadata=json.dumps({"parent_task_id": parent_id}),
    )
    session.add(history)
    session.commit()
    logger.info(
        f"Generated refinement task #{refinement_task.id} for task #{parent_id}: {description[:80]}"
    )
    return refinement_task


def find_recent_completed_tasks(session: Session, hours: int = 24) -> list[Task]:
    """Return recently completed tasks that may need refinement."""
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)
    tasks = (
        session.query(Task)
        .filter(
            Task.completed_at.isnot(None),
            Task.completed_at >= cutoff,
            Task.status == TaskStatus.COMPLETED,
        )
        .order_by(Task.completed_at.desc())
        .all()
    )
    return tasks
