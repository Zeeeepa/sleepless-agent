"""Generate task ideas using Claude AI"""

from typing import Optional

from loguru import logger


class AITaskGenerator:
    """Generate creative task ideas using Claude API"""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize AI task generator

        Args:
            api_key: Optional Anthropic API key. If not provided, uses ANTHROPIC_API_KEY env var.
        """
        self.api_key = api_key
        self._client = None

    def _get_client(self):
        """Lazy load Claude client"""
        if self._client is None:
            try:
                import anthropic

                self._client = anthropic.Anthropic(api_key=self.api_key) if self.api_key else anthropic.Anthropic()
            except ImportError:
                logger.error("anthropic package not installed. Install with: pip install anthropic")
                return None
        return self._client

    def generate_improvement_idea(self, project_context: Optional[str] = None) -> Optional[str]:
        """Generate a creative improvement idea for the project

        Args:
            project_context: Optional context about the project (e.g., "Python CLI tool")

        Returns:
            A task description for a potential improvement
        """
        client = self._get_client()
        if not client:
            return None

        context_text = f"Project context: {project_context}" if project_context else "Generic Python project"

        prompt = f"""You are a software development assistant. Generate ONE specific, actionable improvement idea for a project.

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

        try:
            message = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )

            if message.content and len(message.content) > 0:
                task_description = message.content[0].text.strip()
                return task_description
            return None

        except Exception as e:
            logger.error(f"Failed to generate task with AI: {e}")
            return None

    def generate_from_code_context(self, code_summary: str) -> Optional[str]:
        """Generate improvement idea based on code analysis

        Args:
            code_summary: Summary of code analysis (e.g., "File has 500 lines, 2 classes")

        Returns:
            A task description
        """
        client = self._get_client()
        if not client:
            return None

        prompt = f"""You are a code improvement assistant. Based on this code analysis:
{code_summary}

Generate ONE specific improvement task. Be concise and actionable.
Respond with ONLY the task description, nothing else."""

        try:
            message = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )

            if message.content and len(message.content) > 0:
                return message.content[0].text.strip()
            return None

        except Exception as e:
            logger.debug(f"Failed to generate task from code context: {e}")
            return None
