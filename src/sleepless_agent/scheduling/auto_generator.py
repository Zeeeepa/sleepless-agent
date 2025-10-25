"""Auto-task generation mechanism that creates tasks when usage is below threshold"""

import json
import random
from datetime import datetime
from typing import Optional, TypeAlias

from claude_agent_sdk import (
    AssistantMessage,
    CLIConnectionError,
    CLIJSONDecodeError,
    CLINotFoundError,
    ClaudeAgentOptions,
    ProcessError,
    ResultMessage,
    TextBlock,
    query,
)
from sqlalchemy.orm import Session

from sleepless_agent.monitoring.logging import get_logger

logger = get_logger(__name__)

from sleepless_agent.core.models import Task, TaskPriority, TaskStatus, TaskType, GenerationHistory
from typing import TypeAlias

from sleepless_agent.scheduling.scheduler import BudgetManager
from sleepless_agent.utils.config import ConfigNode

AutoGenerationConfig: TypeAlias = ConfigNode
AutoTaskPromptConfig: TypeAlias = ConfigNode


class AutoTaskGenerator:
    """Generate tasks automatically when Claude Code usage is below configured threshold"""

    def __init__(
        self,
        db_session: Session,
        config: AutoGenerationConfig,
        budget_manager: BudgetManager,
        default_model: str,
        usage_command: str,
        pause_threshold_day: float,
        pause_threshold_night: float,
    ):
        """Initialize auto-generator with database session and config"""
        self.session = db_session
        self.config = config
        self.budget_manager = budget_manager
        self.default_model = default_model
        self.usage_command = usage_command
        self.pause_threshold_day = pause_threshold_day
        self.pause_threshold_night = pause_threshold_night

        # Track generation metadata
        self.last_generation_time: Optional[datetime] = None
        self._last_generation_source: Optional[str] = None

    async def check_and_generate(self) -> bool:
        """Check if conditions are met and generate a task if possible"""
        if not self.config.enabled:
            return False

        # Check usage threshold and ceiling
        if not self._should_generate():
            return False

        # Try to generate a task
        task = await self._generate_task()
        if task:
            logger.info("autogen.task.created", task_id=task.id, preview=task.description[:80], source=self._last_generation_source)
            return True

        return False

    def _should_generate(self) -> bool:
        """Check if usage is below pause threshold (use time-based thresholds)"""
        from sleepless_agent.monitoring.pro_plan_usage import ProPlanUsageChecker
        from sleepless_agent.scheduling.time_utils import is_nighttime

        try:
            checker = ProPlanUsageChecker(command=self.usage_command)
            threshold = self.pause_threshold_night if is_nighttime() else self.pause_threshold_day
            should_pause, _ = checker.check_should_pause(threshold_percent=threshold)

            # Generate only when NOT paused (i.e., usage < threshold)
            return not should_pause
        except Exception as e:
            logger.error("autogen.usage_check.failed", error=str(e))
            # Don't generate on error - fail safe
            return False

    async def _generate_task(self) -> Optional[Task]:
        """Generate a task using the configured prompt archetypes."""
        prompt_config = self._select_prompt()
        if not prompt_config:
            logger.warning("autogen.no_prompt_available")
            return None

        self._last_generation_source = prompt_config.name
        logger.debug("autogen.prompt.begin", prompt=prompt_config.name)

        task_desc = await self._generate_from_prompt(prompt_config)

        if not task_desc:
            return None

        # Parse task type from description (for AI-generated tasks with [NEW]/[REFINE] prefix)
        clean_desc, task_type = self._parse_task_type(task_desc)

        # All auto-generated tasks are low-priority
        priority = TaskPriority.GENERATED

        # Create task in database
        task = Task(
            description=clean_desc,
            priority=priority,
            task_type=task_type,
            status=TaskStatus.PENDING,
            created_at=datetime.utcnow()
        )
        self.session.add(task)
        self.session.flush()  # Get the ID

        # Record in generation history
        usage_percent = self.budget_manager.get_usage_percent()
        history = GenerationHistory(
            task_id=task.id,
            source=prompt_config.name,
            usage_percent_at_generation=usage_percent,
            source_metadata=json.dumps({
                "priority": priority.value,
                "task_type": task_type.value,
                "prompt_name": prompt_config.name,
            })
        )
        self.session.add(history)
        self.session.commit()

        return task

    def _select_prompt(self) -> Optional[AutoTaskPromptConfig]:
        """Select a prompt configuration based on configured weights."""
        prompts = self.config.prompts or []
        weighted_list: list[AutoTaskPromptConfig] = []

        for prompt in prompts:
            weight = max(int(prompt.weight * 10 or 0), 0)  # Scale by 10 for decimal weights
            if weight <= 0:
                continue
            weighted_list.extend([prompt] * weight)

        if not weighted_list:
            return None

        return random.choice(weighted_list)

    @staticmethod
    def _parse_task_type(task_desc: str) -> tuple[str, TaskType]:
        """Parse task description to extract type prefix and clean description

        Args:
            task_desc: Raw task description (may include [NEW] or [REFINE] prefix)

        Returns:
            Tuple of (clean_description, task_type)
        """
        task_desc = task_desc.strip()

        # Check for [NEW] prefix
        if task_desc.upper().startswith("[NEW]"):
            clean_desc = task_desc[5:].strip()
            return (clean_desc, TaskType.NEW)

        # Check for [REFINE] prefix
        if task_desc.upper().startswith("[REFINE]"):
            clean_desc = task_desc[8:].strip()
            return (clean_desc, TaskType.REFINE)

        # Default to NEW if no prefix found
        return (task_desc, TaskType.NEW)

    async def _generate_from_prompt(self, prompt_config: AutoTaskPromptConfig) -> Optional[str]:
        """Execute the configured prompt via Claude and return the response."""
        try:
            return await self._run_prompt(prompt_config)
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.debug(
                "autogen.prompt.execution_failed",
                prompt=prompt_config.name,
                error=str(exc),
            )
            return None

    async def _run_prompt(self, prompt_config: AutoTaskPromptConfig) -> Optional[str]:
        """Stream the Claude response for the configured prompt."""
        prompt_text = prompt_config.prompt.strip()
        if not prompt_text:
            logger.debug("autogen.prompt.empty", prompt=prompt_config.name)
            return None

        options = self._build_options(self.default_model)
        text_segments: list[str] = []

        try:
            async for message in query(prompt=prompt_text, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            text_segments.append(block.text)
                elif isinstance(message, ResultMessage):
                    if message.result:
                        text_segments.append(message.result)
        except (CLINotFoundError, ProcessError, CLIConnectionError, CLIJSONDecodeError) as exc:
            self._log_sdk_failure(exc, prompt_name=prompt_config.name)
            return None
        except Exception as exc:  # pragma: no cover - unexpected failure
            self._log_sdk_failure(exc, prompt_name=prompt_config.name, unexpected=True)
            return None

        full_text = "".join(text_segments).strip()
        return full_text or None

    @staticmethod
    def _build_options(model: str) -> ClaudeAgentOptions:
        """Create Claude SDK options for the prompt run."""
        return ClaudeAgentOptions(model=model)

    @staticmethod
    def _log_sdk_failure(
        exc: Exception,
        *,
        prompt_name: str,
        unexpected: bool = False,
    ) -> None:
        """Emit a structured log entry for Claude SDK failures."""
        event = "claude_sdk.unexpected_error" if unexpected else "claude_sdk.error"
        logger.error(
            event,
            prompt=prompt_name,
            error=str(exc),
            exception_type=exc.__class__.__name__,
        )
