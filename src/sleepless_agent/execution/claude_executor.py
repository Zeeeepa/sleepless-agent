"""Claude API executor for task processing"""

import json
import logging
from typing import Optional

from anthropic import Anthropic

from sleepless_agent.utils.tools import ToolExecutor

logger = logging.getLogger(__name__)

# Task type prompts
TASK_PROMPTS = {
    "code": """You are an expert software engineer. Process the following task:

{description}

You have access to tools to read/write files, execute bash commands, etc. Use them to:
1. Understand the codebase context
2. Implement the solution
3. Test your changes

After making changes, provide a summary of what you did.""",

    "research": """You are a research expert. Process the following task:

{description}

Use available tools to search and analyze code/files as needed. Provide:
1. Key findings and insights
2. Relevant resources/links
3. Actionable recommendations
4. Summary of learnings""",

    "brainstorm": """You are a creative thinking expert. Process the following task:

{description}

Provide:
1. Multiple perspectives/approaches
2. Pros and cons of each
3. Recommendations
4. Next steps to explore""",

    "documentation": """You are a technical writer. Process the following task:

{description}

Use tools to read code/files as needed. Provide:
1. Clear, well-structured content
2. Code examples where relevant
3. Common pitfalls to avoid
4. Quick reference summary""",

    "general": """Process the following task:

{description}

You have access to tools to read files, run commands, etc. Use them as needed.
Provide a thoughtful, comprehensive response.""",
}


class ClaudeExecutor:
    """Execute tasks using Claude API"""

    def __init__(self, api_key: str, model: str = "claude-opus-4-1-20250805", workspace: str = "./workspace"):
        """Initialize Claude executor"""
        self.client = Anthropic(api_key=api_key)
        self.model = model
        self.tool_executor = ToolExecutor(workspace=workspace, allow_bash=True)

    def execute_task(
        self,
        description: str,
        task_type: str = "general",
        context: Optional[dict] = None,
        max_tokens: int = 4096,
    ) -> tuple:
        """Execute task with tool use and return (result_text, files_modified, commands_executed)"""
        try:
            # Build prompt
            prompt_template = TASK_PROMPTS.get(task_type, TASK_PROMPTS["general"])
            prompt = prompt_template.format(description=description)

            # Add context if provided
            if context:
                prompt += f"\n\nContext: {json.dumps(context, indent=2)}"

            logger.info(f"Executing {task_type} task: {description[:50]}...")

            # Prepare tools
            tools = self.tool_executor.get_tools_schema()

            # Get tool schema for Claude
            tool_defs = [
                {
                    "name": tool["name"],
                    "description": tool["description"],
                    "input_schema": tool["input_schema"],
                }
                for tool in tools
            ]

            messages = [{"role": "user", "content": prompt}]
            files_modified = []
            commands_executed = []

            # Agentic loop for tool use
            max_iterations = 10
            for iteration in range(max_iterations):
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    tools=tool_defs,
                    messages=messages,
                )

                # Check if we're done
                if response.stop_reason == "end_turn":
                    break

                # Process tool use
                if response.stop_reason == "tool_use":
                    # Extract tool use blocks
                    assistant_message = {"role": "assistant", "content": response.content}
                    messages.append(assistant_message)

                    tool_results = []
                    for block in response.content:
                        if block.type == "tool_use":
                            tool_name = block.name
                            tool_input = block.input

                            logger.info(f"Tool use: {tool_name} with input: {json.dumps(tool_input)}")

                            # Track file modifications
                            if tool_name in ["write_file", "edit_file"]:
                                files_modified.append(tool_input.get("path", ""))

                            # Track command executions
                            if tool_name == "bash":
                                commands_executed.append(tool_input.get("command", ""))

                            # Execute tool
                            result = self.tool_executor.execute(tool_name, **tool_input)

                            tool_results.append(
                                {
                                    "type": "tool_result",
                                    "tool_use_id": block.id,
                                    "content": json.dumps(result),
                                }
                            )

                    # Add tool results to messages
                    messages.append({"role": "user", "content": tool_results})

                else:
                    # Some other stop reason
                    break

            # Extract final text response
            final_text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    final_text += block.text

            logger.info(f"Task completed successfully")
            return final_text, files_modified, commands_executed

        except Exception as e:
            logger.error(f"Failed to execute task: {e}")
            raise

    def brainstorm(
        self,
        topic: str,
        context: Optional[str] = None,
        max_tokens: int = 2048,
    ) -> str:
        """Brainstorm on a topic"""
        prompt = f"""Brainstorm the following topic and provide creative ideas:

Topic: {topic}"""
        if context:
            prompt += f"\n\nContext: {context}"

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            return message.content[0].text
        except Exception as e:
            logger.error(f"Failed to brainstorm: {e}")
            raise

    def analyze_code(
        self,
        code: str,
        language: str = "python",
        question: str = "Analyze this code",
    ) -> str:
        """Analyze code snippet"""
        prompt = f"""Analyze the following {language} code:

{code}

Question: {question}"""

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            return message.content[0].text
        except Exception as e:
            logger.error(f"Failed to analyze code: {e}")
            raise

    def generate_documentation(
        self,
        code: str,
        language: str = "python",
        style: str = "docstring",
    ) -> str:
        """Generate documentation for code"""
        prompt = f"""Generate {style} documentation for the following {language} code:

{code}

Provide clear, comprehensive documentation."""

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            return message.content[0].text
        except Exception as e:
            logger.error(f"Failed to generate documentation: {e}")
            raise
