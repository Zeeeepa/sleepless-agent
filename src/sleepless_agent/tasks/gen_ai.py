"""Generate task ideas using Claude via the Agent SDK."""

import asyncio
from typing import Optional

from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    AssistantMessage,
    TextBlock,
    ResultMessage,
    CLINotFoundError,
    ProcessError,
    CLIConnectionError,
    CLIJSONDecodeError,
)
from sleepless_agent.monitoring.logging import get_logger
logger = get_logger(__name__)


class AITaskGenerator:
    """Generate creative task ideas using Claude API"""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        """Initialize AI task generator

        Args:
            api_key: Optional Anthropic API key. If not provided, uses ANTHROPIC_API_KEY env var.
        """
        self.api_key = api_key
        self.model = model 

    def _build_options(self) -> ClaudeAgentOptions:
        """Create SDK options for the current run."""
        options_kwargs: dict = {"model": self.model}
        if self.api_key:
            options_kwargs["env"] = {"ANTHROPIC_API_KEY": self.api_key}
        return ClaudeAgentOptions(**options_kwargs)

    async def _run_prompt(self, prompt: str) -> Optional[str]:
        """Execute a prompt via the Agent SDK and return the aggregated text."""
        options = self._build_options()
        text_segments: list[str] = []

        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        text_segments.append(block.text)
            elif isinstance(message, ResultMessage):
                if message.result:
                    text_segments.append(message.result)

        full_text = "".join(text_segments).strip()
        return full_text or None

    async def _run_async(self, prompt: str) -> Optional[str]:
        """Async helper to run the prompt without blocking the caller's event loop."""
        try:
            return await self._run_prompt(prompt)
        except (CLINotFoundError, ProcessError, CLIConnectionError, CLIJSONDecodeError) as exc:
            logger.error(f"Claude Agent SDK error: {exc}")
            return None
        except Exception as exc:  # pragma: no cover - unexpected failure
            logger.error(f"Unexpected error running Claude prompt: {exc}")
            return None

    def _run_sync(self, prompt: str) -> Optional[str]:
        """Helper to run the async prompt execution synchronously."""
        try:
            return asyncio.run(self._run_prompt(prompt))
        except RuntimeError as exc:
            if "asyncio.run()" in str(exc):
                logger.error(
                    "AITaskGenerator cannot run inside an active asyncio event loop. "
                    "Use the async Claude Agent SDK primitives directly in async contexts."
                )
                return None
            raise
        except (CLINotFoundError, ProcessError, CLIConnectionError, CLIJSONDecodeError) as exc:
            logger.error(f"Claude Agent SDK error: {exc}")
            return None
        except Exception as exc:  # pragma: no cover - unexpected failure
            logger.error(f"Unexpected error running Claude prompt: {exc}")
            return None

    def _build_improvement_prompt(self, project_context: Optional[str]) -> str:
        context_text = f"Project context: {project_context}" if project_context else "Generic Python project"

        return f"""You are a software development assistant. Generate ONE specific, actionable improvement idea for a project.

{context_text}

Generate task ideas in categories like:
- Code quality (refactoring, optimization, testing)
- Documentation (docstrings, README, examples)
- Features (new functionality, enhancements)
- Architecture (design improvements, modularity)
- Performance (caching, algorithms, database queries)
- Security (input validation, authentication, encryption)

Respond with ONLY a single task description in 1-2 sentences. Be specific and actionable.
Do NOT include task IDs, bullet points, or explanations. Just the task description.

Example format: "Add caching to the API response handler to reduce database queries by 50%"
"""

    def generate_improvement_idea(self, project_context: Optional[str] = None) -> Optional[str]:
        """Generate a creative improvement idea for the project

        Args:
            project_context: Optional context about the project (e.g., "Python CLI tool")

        Returns:
            A task description for a potential improvement
        """
        prompt = self._build_improvement_prompt(project_context)

        try:
            return self._run_sync(prompt)
        except Exception as e:  # pragma: no cover - unexpected failure
            logger.error(f"Failed to generate task with AI: {e}")
            return None

    async def generate_improvement_idea_async(self, project_context: Optional[str] = None) -> Optional[str]:
        """Async variant of generate_improvement_idea for use within event loops."""
        prompt = self._build_improvement_prompt(project_context)
        try:
            return await self._run_async(prompt)
        except Exception as e:  # pragma: no cover - unexpected failure
            logger.error(f"Failed to generate task with AI: {e}")
            return None

    def _build_code_context_prompt(self, code_summary: str) -> str:
        return f"""You are a code improvement assistant. Based on this code analysis:
{code_summary}

Generate ONE specific improvement task. Be concise and actionable.
Respond with ONLY the task description, nothing else."""

    def generate_from_code_context(self, code_summary: str) -> Optional[str]:
        """Generate improvement idea based on code analysis

        Args:
            code_summary: Summary of code analysis (e.g., "File has 500 lines, 2 classes")

        Returns:
            A task description
        """
        prompt = self._build_code_context_prompt(code_summary)

        try:
            return self._run_sync(prompt)
        except Exception as e:  # pragma: no cover - unexpected failure
            logger.debug(f"Failed to generate task from code context: {e}")
            return None

    async def generate_from_code_context_async(self, code_summary: str) -> Optional[str]:
        """Async variant of generate_from_code_context for use within event loops."""
        prompt = self._build_code_context_prompt(code_summary)
        try:
            return await self._run_async(prompt)
        except Exception as e:  # pragma: no cover - unexpected failure
            logger.debug(f"Failed to generate task from code context: {e}")
            return None