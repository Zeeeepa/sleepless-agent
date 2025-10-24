"""Auto-task generation mechanism that creates tasks when usage is below threshold"""

import json
import random
from datetime import datetime, time
from typing import Optional, Tuple, Dict

from loguru import logger
from sqlalchemy.orm import Session

from pathlib import Path

from sleepless_agent.core.models import Task, TaskPriority, TaskStatus, TaskPool, GenerationHistory
from sleepless_agent.core.scheduler import BudgetManager
from sleepless_agent.core.task_sources.task_pool_manager import TaskPoolManager
from sleepless_agent.core.task_sources.code_analyzer import CodeAnalyzer
from sleepless_agent.core.task_sources.ai_generator import AITaskGenerator
from sleepless_agent.core.task_sources.backlog_integrator import BacklogIntegrator
from sleepless_agent.config import AutoGenerationConfig


class AutoTaskGenerator:
    """Generate tasks automatically when Claude Code usage is below configured threshold"""

    def __init__(
        self,
        db_session: Session,
        config: AutoGenerationConfig,
        budget_manager: BudgetManager,
        workspace_root: Path = Path("./workspace"),
    ):
        """Initialize auto-generator with database session and config"""
        self.session = db_session
        self.config = config
        self.budget_manager = budget_manager

        # Initialize task source managers
        self.task_pool_manager = TaskPoolManager(db_session)
        self.code_analyzer = CodeAnalyzer(workspace_root)
        self.ai_generator = AITaskGenerator()
        self.backlog_integrator = BacklogIntegrator()

        # Track generation rate limiting
        self.last_generation_time: Optional[datetime] = None
        self.generation_count_this_hour = 0
        self.current_hour_start: Optional[datetime] = None

    def check_and_generate(self) -> bool:
        """Check if conditions are met and generate a task if possible"""
        if not self.config.enabled:
            return False

        # Check usage threshold and ceiling
        if not self._should_generate():
            return False

        # Check rate limiting
        if not self._check_rate_limit():
            return False

        # Try to generate a task
        task = self._generate_task()
        if task:
            logger.info(f"Auto-generated task {task.id}: {task.description[:60]}")
            return True

        return False

    def _should_generate(self) -> bool:
        """Check if usage is within the threshold/ceiling range"""
        usage_percent = self.budget_manager.get_usage_percent()

        # Don't generate if above ceiling
        if usage_percent >= self.config.budget_ceiling_percent:
            return False

        # Only generate if below threshold
        if usage_percent < self.config.usage_threshold_percent:
            return True

        return False

    def _check_rate_limit(self) -> bool:
        """Check if we've exceeded rate limit for current time period"""
        now = datetime.utcnow()
        current_hour = now.replace(minute=0, second=0, microsecond=0)

        # Reset counter if we've moved to a new hour
        if self.current_hour_start != current_hour:
            self.current_hour_start = current_hour
            self.generation_count_this_hour = 0

        # Get rate limit based on time of day
        rate_limit = self._get_current_rate_limit()

        if self.generation_count_this_hour >= rate_limit:
            return False

        self.generation_count_this_hour += 1
        return True

    def _get_current_rate_limit(self) -> int:
        """Get rate limit for current time (night vs day)"""
        now = datetime.utcnow()
        current_hour = now.hour

        # Night: 8 PM (20:00) to 8 AM (08:00)
        if current_hour >= 20 or current_hour < 8:
            return self.config.rate_limit_night
        else:
            return self.config.rate_limit_day

    def _generate_task(self) -> Optional[Task]:
        """Generate a task from selected source"""
        # Select source based on weights
        source = self._select_source()

        logger.debug(f"Generating task from source: {source}")

        if source == "pool":
            task_desc = self._get_from_pool()
        elif source == "code":
            task_desc = self._generate_from_code_analysis()
        elif source == "ai":
            task_desc = self._generate_from_ai()
        elif source == "backlog":
            task_desc = self._generate_from_backlog()
        else:
            logger.warning(f"Unknown source: {source}")
            return None

        if not task_desc:
            return None

        # Determine priority: mostly low-priority generated work unless escalated
        priority = TaskPriority.GENERATED if random.random() < self.config.random_ratio else TaskPriority.SERIOUS

        # Create task in database
        task = Task(
            description=task_desc,
            priority=priority,
            status=TaskStatus.PENDING,
            created_at=datetime.utcnow()
        )
        self.session.add(task)
        self.session.flush()  # Get the ID

        # Record in generation history
        usage_percent = self.budget_manager.get_usage_percent()
        history = GenerationHistory(
            task_id=task.id,
            source=source,
            usage_percent_at_generation=usage_percent,
            source_metadata=json.dumps({"priority": priority.value})
        )
        self.session.add(history)
        self.session.commit()

        return task

    def _select_source(self) -> str:
        """Select a source based on configured weights"""
        weights = self.config.source_weights
        sources = list(weights.keys())
        weighted_list = []

        for source in sources:
            weighted_list.extend([source] * weights[source])

        return random.choice(weighted_list)

    def _get_from_pool(self) -> Optional[str]:
        """Get a task from the predefined task pool"""
        return self.task_pool_manager.get_next_task()

    def _generate_from_code_analysis(self) -> Optional[str]:
        """Generate task by analyzing code for TODOs, FIXMEs, etc."""
        try:
            return self.code_analyzer.generate_task_idea()
        except Exception as e:
            logger.debug(f"Code analysis failed: {e}")
            return None

    def _generate_from_ai(self) -> Optional[str]:
        """Generate task using AI/Claude API"""
        try:
            return self.ai_generator.generate_improvement_idea()
        except Exception as e:
            logger.debug(f"AI generation failed: {e}")
            return None

    def _generate_from_backlog(self) -> Optional[str]:
        """Generate task from project backlog (GitHub issues, etc.)"""
        try:
            return self.backlog_integrator.get_issue_from_github(labels=["good first issue"])
        except Exception as e:
            logger.debug(f"Backlog integration failed: {e}")
            return None

    def get_generation_stats(self) -> Dict:
        """Get statistics about auto-generated tasks"""
        total = self.session.query(GenerationHistory).count()
        by_source = {}

        for source in ["pool", "code", "ai", "backlog"]:
            count = self.session.query(GenerationHistory).filter(
                GenerationHistory.source == source
            ).count()
            by_source[source] = count

        return {
            "total_generated": total,
            "by_source": by_source,
            "enabled": self.config.enabled,
            "threshold_percent": self.config.usage_threshold_percent,
            "ceiling_percent": self.config.budget_ceiling_percent,
        }
