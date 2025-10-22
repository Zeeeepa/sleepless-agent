"""Claude Code SDK executor for task processing"""

import logging
import subprocess
import time
from pathlib import Path
from typing import Optional, Tuple, List

from claude_agent_sdk import (
    query,
    ClaudeAgentOptions,
    CLINotFoundError,
    ProcessError,
    CLIJSONDecodeError,
    AssistantMessage,
    ToolUseBlock,
    ToolResultBlock,
    ResultMessage,
    TextBlock,
)

logger = logging.getLogger(__name__)


class ClaudeCodeExecutor:
    """Execute tasks using Claude Code CLI via Python Agent SDK"""

    def __init__(
        self,
        workspace_root: str = "./workspace",
        default_timeout: int = 3600,
    ):
        """Initialize Claude Code executor

        Args:
            workspace_root: Root directory for task workspaces
            default_timeout: Default timeout in seconds (not used by SDK directly)
        """
        self.workspace_root = Path(workspace_root)
        self.default_timeout = default_timeout
        self.workspace_root.mkdir(parents=True, exist_ok=True)

        # Verify Claude Code is available
        self._verify_claude_cli()

        logger.info(f"ClaudeCodeExecutor initialized with workspace: {self.workspace_root}")

    def _verify_claude_cli(self):
        """Verify Claude Code CLI is available"""
        try:
            result = subprocess.run(
                ["claude", "--version"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                logger.info("Claude Code CLI verified successfully")
            else:
                raise CLINotFoundError()

        except (FileNotFoundError, subprocess.TimeoutExpired):
            logger.error("Claude Code CLI not found")
            raise RuntimeError(
                "Claude Code CLI not found. "
                "Please install with: npm install -g @anthropic-ai/claude-code"
            )
        except Exception as e:
            logger.warning(f"Could not verify Claude Code CLI: {e}")
            # Don't fail initialization - let it fail on actual execution if needed

    def create_task_workspace(self, task_id: int, init_git: bool = False) -> Path:
        """Create isolated workspace for task

        Args:
            task_id: Task ID
            init_git: Whether to initialize git repo in workspace

        Returns:
            Path to created workspace
        """
        workspace = self.workspace_root / f"task_{task_id}"
        workspace.mkdir(parents=True, exist_ok=True)

        # Optionally initialize git
        if init_git:
            try:
                import subprocess
                subprocess.run(
                    ["git", "init"],
                    cwd=workspace,
                    capture_output=True,
                    check=True,
                )
                # Set initial commit
                subprocess.run(
                    ["git", "config", "user.email", "sleepless-agent@local"],
                    cwd=workspace,
                    capture_output=True,
                )
                subprocess.run(
                    ["git", "config", "user.name", "Sleepless Agent"],
                    cwd=workspace,
                    capture_output=True,
                )
                logger.info(f"Initialized git in workspace: {workspace}")
            except Exception as e:
                logger.warning(f"Failed to initialize git in workspace: {e}")

        logger.info(f"Created workspace: {workspace}")
        return workspace

    async def execute_task(
        self,
        task_id: int,
        description: str,
        task_type: str = "general",
        priority: str = "random",
        timeout: Optional[int] = None,
    ) -> Tuple[str, List[str], List[str], int]:
        """Execute task with Claude Code SDK

        Args:
            task_id: Task ID
            description: Task description/prompt
            task_type: Type of task (code, research, brainstorm, etc.)
            priority: Task priority (random or serious)
            timeout: Timeout in seconds (not directly supported by SDK)

        Returns:
            Tuple of (output_text, files_modified, commands_executed, exit_code)
        """
        timeout = timeout or self.default_timeout

        try:
            # Create workspace
            init_git = (priority == "serious")
            workspace = self.create_task_workspace(task_id, init_git)

            # Build enhanced prompt
            prompt = self._build_prompt(description, task_type, priority)

            # Track files before execution
            files_before = self._get_workspace_files(workspace)

            # Track tool usage
            files_modified = set()
            commands_executed = []
            output_parts = []
            success = True

            # Execute Claude Code via SDK
            logger.info(f"Executing Claude Code SDK for task {task_id}...")
            start_time = time.time()

            options = ClaudeAgentOptions(
                cwd=str(workspace),
                allowed_tools=[
                    "Read", "Write", "Edit", "Bash", "Glob", "Grep",
                    "TodoWrite", "BashOutput", "KillBash"
                ],
                permission_mode="acceptEdits" if priority == "serious" else "acceptEdits",
                max_turns=20,  # Limit turns to prevent infinite loops
            )

            # Process message stream
            async for message in query(prompt=prompt, options=options):
                # Handle AssistantMessage with content blocks
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            output_parts.append(block.text)
                        elif isinstance(block, ToolUseBlock):
                            # Track tool usage
                            logger.info(f"Tool used: {block.name}")

                            if block.name in ["Write", "Edit"]:
                                file_path = block.input.get("file_path", "")
                                if file_path:
                                    files_modified.add(file_path)

                            elif block.name == "Bash":
                                command = block.input.get("command", "")
                                if command:
                                    commands_executed.append(command)

                # Handle ResultMessage (final result)
                elif isinstance(message, ResultMessage):
                    success = not message.is_error
                    if message.result:
                        output_parts.append(f"\n[Result: {message.result}]")

                    logger.info(
                        f"Task {task_id} completed in {message.duration_ms}ms "
                        f"(API time: {message.duration_api_ms}ms, turns: {message.num_turns})"
                    )

                    if message.total_cost_usd is not None:
                        logger.info(f"Task cost: ${message.total_cost_usd:.4f}")

            execution_time = int(time.time() - start_time)

            # Combine output
            output_text = "\n".join(output_parts)

            # Track files after execution
            files_after = self._get_workspace_files(workspace)
            new_files = files_after - files_before

            # Combine tracked modifications with detected new files
            all_modified_files = sorted(list(files_modified.union(new_files)))

            # Exit code: 0 for success, 1 for error
            exit_code = 0 if success else 1

            logger.info(
                f"Task {task_id} completed in {execution_time}s "
                f"(exit code: {exit_code}, files: {len(all_modified_files)})"
            )

            return output_text, all_modified_files, commands_executed, exit_code

        except CLINotFoundError:
            logger.error("Claude Code CLI not found")
            raise RuntimeError(
                "Claude Code CLI not found. "
                "Please install with: npm install -g @anthropic-ai/claude-code"
            )
        except ProcessError as e:
            logger.error(f"Claude Code process error: {e}")
            raise RuntimeError(f"Claude Code process failed: {e}")
        except CLIJSONDecodeError as e:
            logger.error(f"Failed to parse Claude Code output: {e}")
            raise RuntimeError(f"Failed to parse Claude Code output: {e}")
        except Exception as e:
            logger.error(f"Failed to execute task {task_id}: {e}")
            raise

    def _build_prompt(self, description: str, task_type: str, priority: str) -> str:
        """Build enhanced prompt for Claude Code

        Args:
            description: Task description
            task_type: Type of task
            priority: Task priority

        Returns:
            Enhanced prompt string
        """
        # Task type specific instructions
        type_instructions = {
            "code": """You are an expert software engineer. Use the available tools to:
1. Read and understand relevant code
2. Implement the solution
3. Test your changes
4. Provide clear documentation""",

            "research": """You are a research expert. Use tools to:
1. Search and analyze files
2. Extract key information
3. Provide insights and recommendations
4. Summarize your findings""",

            "brainstorm": """You are a creative thinker. Brainstorm ideas:
1. Explore multiple approaches
2. Consider pros and cons
3. Recommend next steps
4. Think outside the box""",

            "documentation": """You are a technical writer. Create documentation:
1. Read code as needed
2. Write clear, structured content
3. Include examples and best practices
4. Make it accessible""",

            "general": """Process the following task using available tools as needed.
Be thorough, methodical, and provide clear explanations.""",
        }

        instructions = type_instructions.get(task_type, type_instructions["general"])

        # Priority-specific notes
        if priority == "serious":
            priority_note = """
⚠️  IMPORTANT: This is a SERIOUS task requiring careful implementation.
- Write production-quality code
- Test your changes thoroughly
- Follow best practices and conventions
- Commit your work with clear messages when done
"""
        else:
            priority_note = """
💡 NOTE: This is a RANDOM THOUGHT - feel free to experiment!
- Try creative approaches
- It's okay to be experimental
- Have fun with it!
"""

        # Build full prompt
        prompt = f"""{instructions}

{priority_note}

TASK:
{description}

Please complete this task and provide a summary of what you did at the end.
"""

        return prompt

    def _get_workspace_files(self, workspace: Path) -> set:
        """Get set of all files in workspace (excluding metadata and .git)

        Args:
            workspace: Workspace path

        Returns:
            Set of relative file paths
        """
        files = set()
        exclude_patterns = {
            ".git",
            ".gitignore",
            "__pycache__",
            ".DS_Store",
            "node_modules",
        }

        try:
            for path in workspace.rglob("*"):
                if path.is_file():
                    # Check if any parent or the file itself should be excluded
                    relative_path = path.relative_to(workspace)
                    parts = set(relative_path.parts)

                    # Check for excluded patterns
                    should_exclude = False
                    for pattern in exclude_patterns:
                        if pattern in parts or relative_path.name == pattern:
                            should_exclude = True
                            break
                        # Check for .git directory in path
                        if any(part.startswith(".git") for part in parts):
                            should_exclude = True
                            break

                    if not should_exclude:
                        files.add(str(relative_path))
        except Exception as e:
            logger.warning(f"Error scanning workspace files: {e}")

        return files

    def cleanup_workspace(self, task_id: int, force: bool = False):
        """Clean up task workspace

        Args:
            task_id: Task ID
            force: Force cleanup even if files exist (default: False)
        """
        workspace = self.workspace_root / f"task_{task_id}"

        if not workspace.exists():
            logger.debug(f"Workspace does not exist: {workspace}")
            return

        try:
            # Check if workspace is empty or force cleanup
            contents = list(workspace.iterdir())
            if force or len(contents) == 0:
                import shutil
                shutil.rmtree(workspace)
                logger.info(f"Cleaned up workspace: {workspace}")
            else:
                logger.debug(f"Workspace not empty, skipping cleanup: {workspace}")
        except Exception as e:
            logger.error(f"Failed to cleanup workspace {workspace}: {e}")

    def get_workspace_path(self, task_id: int) -> Path:
        """Get path to task workspace

        Args:
            task_id: Task ID

        Returns:
            Path to workspace
        """
        return self.workspace_root / f"task_{task_id}"

    def workspace_exists(self, task_id: int) -> bool:
        """Check if workspace exists for task

        Args:
            task_id: Task ID

        Returns:
            True if workspace exists
        """
        return self.get_workspace_path(task_id).exists()
