"""Claude Code CLI executor for task processing"""

import json
import logging
import subprocess
import time
from pathlib import Path
from typing import Optional, Tuple, List

logger = logging.getLogger(__name__)


class ClaudeCodeExecutor:
    """Execute tasks using Claude Code CLI"""

    def __init__(
        self,
        workspace_root: str = "./workspace",
        claude_binary: str = "claude",
        default_timeout: int = 3600,
    ):
        """Initialize Claude Code executor

        Args:
            workspace_root: Root directory for task workspaces
            claude_binary: Path to claude binary (default: "claude" from PATH)
            default_timeout: Default timeout in seconds
        """
        self.workspace_root = Path(workspace_root)
        self.claude_binary = claude_binary
        self.default_timeout = default_timeout
        self.workspace_root.mkdir(parents=True, exist_ok=True)

        # Verify Claude Code is available
        self._verify_claude_binary()

        logger.info(f"ClaudeCodeExecutor initialized with workspace: {self.workspace_root}")

    def _verify_claude_binary(self):
        """Verify Claude Code binary is available"""
        try:
            result = subprocess.run(
                [self.claude_binary, "--version"],
                capture_output=True,
                timeout=5,
                text=True,
            )
            if result.returncode == 0:
                logger.info(f"Claude Code CLI found: {result.stdout.strip()}")
            else:
                logger.warning(f"Claude Code CLI check returned non-zero: {result.returncode}")
        except FileNotFoundError:
            logger.error(f"Claude Code binary not found: {self.claude_binary}")
            raise RuntimeError(
                f"Claude Code CLI not found at '{self.claude_binary}'. "
                "Please install Claude Code or set the correct binary path in config."
            )
        except Exception as e:
            logger.error(f"Failed to verify Claude Code binary: {e}")
            raise

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
            except subprocess.CalledProcessError as e:
                logger.warning(f"Failed to initialize git in workspace: {e}")

        logger.info(f"Created workspace: {workspace}")
        return workspace

    def execute_task(
        self,
        task_id: int,
        description: str,
        task_type: str = "general",
        priority: str = "random",
        timeout: Optional[int] = None,
    ) -> Tuple[str, List[str], List[str], int]:
        """Execute task with Claude Code

        Args:
            task_id: Task ID
            description: Task description/prompt
            task_type: Type of task (code, research, brainstorm, etc.)
            priority: Task priority (random or serious)
            timeout: Timeout in seconds (default: self.default_timeout)

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

            # Write prompt to file
            prompt_file = workspace / "task_prompt.txt"
            prompt_file.write_text(prompt, encoding="utf-8")

            # Track files before execution
            files_before = self._get_workspace_files(workspace)

            # Execute Claude Code
            logger.info(f"Executing Claude Code for task {task_id} (timeout: {timeout}s)...")
            start_time = time.time()

            result = subprocess.run(
                [self.claude_binary, "chat", "-f", str(prompt_file)],
                cwd=workspace,
                capture_output=True,
                timeout=timeout,
                text=True,
            )

            execution_time = int(time.time() - start_time)

            # Capture output
            stdout = result.stdout
            stderr = result.stderr
            exit_code = result.returncode

            # Save outputs
            (workspace / "claude_output.txt").write_text(stdout, encoding="utf-8")
            if stderr:
                (workspace / "claude_error.txt").write_text(stderr, encoding="utf-8")

            # Track files after execution
            files_after = self._get_workspace_files(workspace)
            files_modified = sorted(list(files_after - files_before))

            # Extract commands executed (best effort from output)
            commands_executed = self._extract_commands(stdout)

            logger.info(
                f"Task {task_id} completed in {execution_time}s "
                f"(exit code: {exit_code}, files modified: {len(files_modified)})"
            )

            # Log warning if non-zero exit code
            if exit_code != 0:
                logger.warning(f"Task {task_id} exited with code {exit_code}")
                if stderr:
                    logger.warning(f"stderr: {stderr[:500]}")

            return stdout, files_modified, commands_executed, exit_code

        except subprocess.TimeoutExpired:
            logger.error(f"Task {task_id} timed out after {timeout}s")
            raise TimeoutError(f"Task execution timed out after {timeout}s")
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
            "task_prompt.txt",
            "claude_output.txt",
            "claude_error.txt",
            ".git",
            ".gitignore",
            "__pycache__",
            ".DS_Store",
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

    def _extract_commands(self, output: str) -> List[str]:
        """Extract bash commands from Claude Code output

        This is a heuristic - Claude Code doesn't explicitly report commands.
        We try to extract from common patterns in the output.

        Args:
            output: Claude Code stdout

        Returns:
            List of extracted commands
        """
        commands = []

        # Look for common bash execution patterns in output
        # This is best-effort and may not catch everything
        lines = output.split('\n')

        for i, line in enumerate(lines):
            # Look for lines that indicate bash execution
            if 'bash' in line.lower() or 'command' in line.lower() or '$' in line:
                # Try to extract the actual command
                # This is very heuristic and may need refinement
                stripped = line.strip()
                if stripped.startswith('$'):
                    commands.append(stripped[1:].strip())

        return commands

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
