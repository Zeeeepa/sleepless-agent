# Claude Code Integration - Redesign Plan

## Overview

Redesign the Sleepless Agent to use **Claude Code CLI** instead of direct Claude API calls, while maintaining the core functionality of a 24/7 daemon that processes tasks via Slack.

## What Stays

### Core Architecture ✓
- Slack bot interface and all slash commands
- SQLite-backed task queue with CRUD operations
- Two-tier priority system (random thoughts + serious jobs)
- Smart scheduler with priority-based selection
- Git automation (auto-commits + PR creation)
- Monitoring and health checks
- Result storage (database + JSON files)
- Performance logging

### Components to Keep
- `src/bot.py` - Slack interface (minimal changes)
- `src/task_queue.py` - Task management (no changes)
- `src/scheduler.py` - Smart scheduling (minor changes)
- `src/git_manager.py` - Git operations (changes for workspace isolation)
- `src/monitor.py` - Health monitoring (no changes)
- `src/results.py` - Result storage (no changes)
- `src/models.py` - Data models (minor additions)
- `sleepless_agent/daemon.py` - Main loop (changes for new executor)

## What Changes

### Major Changes

#### 1. Replace ClaudeExecutor (src/claude_executor.py)
**Current:** Direct Anthropic API calls with tool use loop
**New:** Spawn `claude` CLI subprocess with prompt input

#### 2. Remove ToolExecutor (src/tools.py)
**Current:** Custom tools for file operations and bash commands
**New:** Claude Code has built-in tools, no custom implementation needed

#### 3. Add Workspace Isolation
**Current:** Single shared workspace directory
**New:** Isolated workspace per task: `workspace/task_{id}/`

#### 4. Update Configuration (src/config.py)
**Current:** Requires `ANTHROPIC_API_KEY`
**New:** No API key needed, optional Claude Code binary path

## Detailed Design

### 1. Claude Code Invocation Strategy

Three approaches considered:

#### Option A: File-based Prompts (RECOMMENDED)
```python
# Create prompt file
prompt_file = workspace / "task_prompt.txt"
prompt_file.write_text(task_description)

# Invoke Claude Code
result = subprocess.run(
    ["claude", "chat", "-f", str(prompt_file)],
    cwd=workspace,
    capture_output=True,
    timeout=task_timeout,
    text=True,
)
```

**Pros:**
- Clean separation of prompt and execution
- Easy to debug (can inspect prompt files)
- Works well with long prompts
- Can preserve prompts for auditing

**Cons:**
- Requires file I/O for each task

#### Option B: Stdin Piping
```python
result = subprocess.run(
    ["claude", "chat"],
    input=task_description,
    cwd=workspace,
    capture_output=True,
    timeout=task_timeout,
    text=True,
)
```

**Pros:**
- No intermediate files
- Simple implementation

**Cons:**
- Harder to debug
- May have issues with very long prompts

#### Option C: Interactive Mode (NOT RECOMMENDED)
Use `pexpect` to interact with Claude Code interactively.

**Cons:**
- Too complex
- Harder to manage timeouts
- Fragile

**Decision: Use Option A (File-based prompts)**

### 2. Workspace Isolation Architecture

#### Directory Structure
```
workspace/
├── task_1/                      # Isolated workspace for task 1
│   ├── .git/                    # Git repo (if needed)
│   ├── task_prompt.txt          # Task description/prompt
│   ├── claude_output.txt        # Claude's stdout
│   ├── claude_error.txt         # Claude's stderr
│   └── <task work files>        # Files created by Claude Code
├── task_2/                      # Isolated workspace for task 2
│   └── ...
└── shared/                      # Optional shared resources
    └── ...
```

#### Workspace Lifecycle
1. **Create:** Before task execution, create `workspace/task_{id}/`
2. **Initialize:** Optionally init git repo if task is "serious"
3. **Execute:** Run Claude Code with this as working directory
4. **Capture:** Collect all modified files
5. **Archive:** For random thoughts, optionally clean up after commit
6. **Preserve:** For serious jobs, keep workspace until PR merged

#### Benefits
- Full isolation - tasks don't interfere
- Easy cleanup
- Can run multiple tasks truly in parallel (no file conflicts)
- Git operations are isolated
- Can preserve entire workspace for debugging

### 3. ClaudeCodeExecutor Implementation

#### New Class: `src/claude_code_executor.py`

```python
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

    def create_task_workspace(self, task_id: int, init_git: bool = False) -> Path:
        """Create isolated workspace for task"""
        workspace = self.workspace_root / f"task_{task_id}"
        workspace.mkdir(parents=True, exist_ok=True)

        # Optionally initialize git
        if init_git:
            subprocess.run(
                ["git", "init"],
                cwd=workspace,
                capture_output=True,
            )

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
            prompt_file.write_text(prompt)

            # Track files before execution
            files_before = self._get_workspace_files(workspace)

            # Execute Claude Code
            logger.info(f"Executing Claude Code for task {task_id}...")
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
            (workspace / "claude_output.txt").write_text(stdout)
            if stderr:
                (workspace / "claude_error.txt").write_text(stderr)

            # Track files after execution
            files_after = self._get_workspace_files(workspace)
            files_modified = list(files_after - files_before)

            # Extract commands executed (if possible from output)
            commands_executed = self._extract_commands(stdout)

            logger.info(
                f"Task {task_id} completed in {execution_time}s "
                f"(exit code: {exit_code}, files: {len(files_modified)})"
            )

            return stdout, files_modified, commands_executed, exit_code

        except subprocess.TimeoutExpired:
            logger.error(f"Task {task_id} timed out after {timeout}s")
            raise
        except Exception as e:
            logger.error(f"Failed to execute task {task_id}: {e}")
            raise

    def _build_prompt(self, description: str, task_type: str, priority: str) -> str:
        """Build enhanced prompt for Claude Code"""

        # Task type specific instructions
        type_instructions = {
            "code": """You are an expert software engineer. Use the available tools to:
1. Read and understand relevant code
2. Implement the solution
3. Test your changes""",

            "research": """You are a research expert. Use tools to:
1. Search and analyze files
2. Extract key information
3. Provide insights and recommendations""",

            "brainstorm": """You are a creative thinker. Brainstorm ideas:
1. Explore multiple approaches
2. Consider pros and cons
3. Recommend next steps""",

            "documentation": """You are a technical writer. Create documentation:
1. Read code as needed
2. Write clear, structured content
3. Include examples""",

            "general": "Process the following task using available tools as needed.",
        }

        instructions = type_instructions.get(task_type, type_instructions["general"])

        # Priority-specific notes
        if priority == "serious":
            priority_note = """
IMPORTANT: This is a SERIOUS task requiring careful implementation.
- Write production-quality code
- Test your changes thoroughly
- Commit your work with clear messages
"""
        else:
            priority_note = """
NOTE: This is a RANDOM THOUGHT - feel free to experiment!
- Try creative approaches
- It's okay to be experimental
"""

        # Build full prompt
        prompt = f"""{instructions}

{priority_note}

TASK:
{description}

Please complete this task and provide a summary of what you did.
"""

        return prompt

    def _get_workspace_files(self, workspace: Path) -> set:
        """Get set of all files in workspace (excluding .git and task metadata)"""
        files = set()
        exclude_patterns = {"task_prompt.txt", "claude_output.txt", "claude_error.txt", ".git"}

        for path in workspace.rglob("*"):
            if path.is_file():
                # Check if any parent is in exclude patterns
                if not any(part in exclude_patterns or part.startswith(".git")
                          for part in path.parts):
                    # Store relative path
                    files.add(str(path.relative_to(workspace)))

        return files

    def _extract_commands(self, output: str) -> List[str]:
        """Extract bash commands from Claude Code output

        This is a heuristic - Claude Code doesn't explicitly report commands.
        We can try to parse from output or just return empty list.
        """
        # TODO: Implement command extraction if needed
        # For now, return empty list
        return []

    def cleanup_workspace(self, task_id: int, force: bool = False):
        """Clean up task workspace

        Args:
            task_id: Task ID
            force: Force cleanup even if files exist
        """
        workspace = self.workspace_root / f"task_{task_id}"

        if workspace.exists() and (force or len(list(workspace.iterdir())) == 0):
            import shutil
            shutil.rmtree(workspace)
            logger.info(f"Cleaned up workspace: {workspace}")
```

### 4. Configuration Changes

#### Updated `src/config.py`

```python
class ClaudeCodeConfig(BaseSettings):
    """Claude Code CLI configuration"""
    binary_path: str = "claude"  # Path to claude binary
    default_timeout: int = 3600   # 1 hour default timeout
    cleanup_random_workspaces: bool = True  # Clean up after random tasks
    preserve_serious_workspaces: bool = True  # Keep serious task workspaces

class AgentConfig(BaseSettings):
    """Agent configuration"""
    workspace_root: Path = Path("./workspace")  # Root for isolated workspaces
    shared_workspace: Path = Path("./workspace/shared")  # Optional shared files
    db_path: Path = Path("./data/tasks.db")
    results_path: Path = Path("./data/results")
    max_parallel_tasks: int = 3
    task_timeout_seconds: int = 3600
```

Remove `ClaudeConfig` with API key requirement.

### 5. Daemon Integration Changes

#### Updated `sleepless_agent/daemon.py` - `SleepleassAgent.__init__()`

```python
def __init__(self):
    """Initialize agent"""
    self.config = get_config()
    self.running = False

    # Initialize components
    self._init_directories()
    self.task_queue = TaskQueue(str(self.config.agent.db_path))
    self.scheduler = SmartScheduler(
        task_queue=self.task_queue,
        max_parallel_tasks=self.config.agent.max_parallel_tasks,
    )

    # NEW: Use Claude Code executor instead
    self.claude = ClaudeCodeExecutor(
        workspace_root=str(self.config.agent.workspace_root),
        claude_binary=self.config.claude_code.binary_path,
        default_timeout=self.config.claude_code.default_timeout,
    )

    self.results = ResultManager(
        str(self.config.agent.db_path),
        str(self.config.agent.results_path),
    )

    # Git manager now works with isolated workspaces
    self.git = GitManager(workspace_root=str(self.config.agent.workspace_root))

    # ... rest of initialization
```

#### Updated `sleepless_agent/daemon.py` - `_execute_task()`

```python
async def _execute_task(self, task):
    """Execute a single task"""
    try:
        # Mark as in progress
        self.task_queue.mark_in_progress(task.id)

        logger.info(f"Executing task {task.id}: {task.description[:50]}...")

        # Execute with Claude Code
        start_time = time.time()
        result_output, files_modified, commands_executed, exit_code = self.claude.execute_task(
            task_id=task.id,
            description=task.description,
            task_type="general",
            priority=task.priority.value,
            timeout=self.config.agent.task_timeout_seconds,
        )
        processing_time = int(time.time() - start_time)

        # Check if execution was successful
        if exit_code != 0:
            raise Exception(f"Claude Code exited with code {exit_code}")

        # Get task workspace for git operations
        task_workspace = self.config.agent.workspace_root / f"task_{task.id}"

        # Handle git operations based on priority
        git_commit_sha = None
        git_pr_url = None
        git_branch = None

        if task.priority == TaskPriority.RANDOM:
            # Auto-commit random thoughts from task workspace
            git_commit_sha = self.git.commit_random_thought(
                task_id=task.id,
                task_workspace=task_workspace,
                description=task.description,
                result_content=result_output,
            )

            # Clean up workspace if configured
            if self.config.claude_code.cleanup_random_workspaces:
                self.claude.cleanup_workspace(task.id, force=True)

        elif task.priority == TaskPriority.SERIOUS and files_modified:
            # For serious tasks, workspace already has git repo
            # Validate and commit in workspace
            is_valid, validation_msg = self.git.validate_changes(
                task_workspace, files_modified
            )

            if is_valid:
                git_branch = f"task-{task.id}"
                git_commit_sha = self.git.commit_in_workspace(
                    workspace=task_workspace,
                    files=files_modified,
                    message=f"Implement task: {task.description[:60]}",
                )

                # Create PR
                git_pr_url = self.git.create_pr_from_workspace(
                    task_workspace=task_workspace,
                    task_id=task.id,
                    task_description=task.description,
                    branch=git_branch,
                )
            else:
                logger.warning(f"Validation failed for task {task.id}: {validation_msg}")

        # Save result
        result = self.results.save_result(
            task_id=task.id,
            output=result_output,
            files_modified=files_modified,
            commands_executed=commands_executed,
            processing_time_seconds=processing_time,
            git_commit_sha=git_commit_sha,
            git_pr_url=git_pr_url,
            git_branch=git_branch,
            workspace_path=str(task_workspace),  # NEW: store workspace location
        )

        # ... rest of completion handling
```

### 6. Git Manager Changes

#### Updated `src/git_manager.py`

Need to add methods for:
- Working with isolated workspaces
- Copying changes from workspace to main repo (for random thoughts)
- Pushing from workspace repo (for serious tasks)

```python
class GitManager:
    """Manage git operations for task workspaces"""

    def __init__(self, workspace_root: str = "./workspace"):
        """Initialize git manager

        Args:
            workspace_root: Root directory containing task workspaces
        """
        self.workspace_root = Path(workspace_root)
        self.main_repo_path = Path.cwd()  # Sleepless agent repo itself

    def commit_random_thought(
        self,
        task_id: int,
        task_workspace: Path,
        description: str,
        result_content: str,
    ) -> Optional[str]:
        """Commit random thought to main repo's random-ideas branch

        Copies files from task workspace to main repo and commits.
        """
        # Implementation: copy files, switch to random-ideas branch, commit
        pass

    def commit_in_workspace(
        self,
        workspace: Path,
        files: List[str],
        message: str,
    ) -> Optional[str]:
        """Commit files in the task workspace itself"""
        # Implementation: git add, git commit in workspace
        pass

    def create_pr_from_workspace(
        self,
        task_workspace: Path,
        task_id: int,
        task_description: str,
        branch: str,
    ) -> Optional[str]:
        """Push workspace branch and create PR"""
        # Implementation: git push, gh pr create
        pass
```

### 7. Scheduler Changes

#### Remove Credit Tracking?

Since we're not using the Claude API, we don't have direct costs per task.
However, we might want to keep it for:
- Rate limiting (don't spam Claude Code)
- Resource management (CPU/memory limits)

**Decision:** Keep credit tracking but make it optional/configurable.

## Implementation Phases

### Phase 1: Core Executor ⚡
1. Implement `ClaudeCodeExecutor` class
2. Add workspace isolation
3. Write unit tests for executor

### Phase 2: Integration 🔌
1. Update `daemon.py` to use new executor
2. Update `config.py` (remove API key, add Claude Code settings)
3. Remove `tools.py` dependency
4. Update requirements.txt (remove anthropic package)

### Phase 3: Git Operations 📦
1. Update `GitManager` for workspace isolation
2. Implement random thought commits (copy from workspace)
3. Implement serious task PRs (push from workspace)
4. Add workspace cleanup logic

### Phase 4: Testing & Polish ✨
1. End-to-end testing with Slack
2. Test parallel task execution
3. Update documentation
4. Add workspace management commands to Makefile

### Phase 5: Optional Enhancements 🚀
1. Shared workspace for common resources
2. Workspace archiving (zip old workspaces)
3. Claude Code output parsing (extract metrics)
4. Support for different Claude Code modes/flags

## Migration Path

### For Users

1. Remove `ANTHROPIC_API_KEY` from `.env`
2. Ensure `claude` CLI is installed and in PATH
3. Update config if using custom Claude Code binary location
4. Run database migration (if schema changes)
5. Restart daemon

### Backward Compatibility

No backward compatibility needed - this is a breaking redesign.
All existing tasks in queue will work with new executor.

## Testing Strategy

### Unit Tests
- `test_claude_code_executor.py` - Test executor in isolation
- Mock subprocess calls
- Test workspace creation/cleanup
- Test prompt building

### Integration Tests
- End-to-end task execution
- Slack command integration
- Git operations with workspaces
- Parallel task execution

### Manual Testing
- Run simple tasks via Slack
- Test random thoughts (should auto-commit)
- Test serious tasks (should create PR)
- Test workspace cleanup
- Test error handling (timeout, Claude Code failure)

## Open Questions

### 1. Claude Code Binary Detection
- How to detect if Claude Code is installed?
- Should we validate on startup?
- Provide helpful error message if not found?

**Proposal:** Check on startup, fail fast with clear message

### 2. Workspace Retention
- How long to keep workspaces?
- Automatic cleanup after X days?
- Manual cleanup command?

**Proposal:**
- Random: clean immediately after commit (configurable)
- Serious: keep until PR merged (manual cleanup command)

### 3. Shared Resources
- Do tasks need access to shared files/context?
- Should we have a `workspace/shared/` directory?
- How to sync common code/libraries?

**Proposal:** Implement `workspace/shared/` as optional feature

### 4. Claude Code Output Parsing
- Can we extract structured data from output?
- Track which tools Claude Code used?
- Extract performance metrics?

**Proposal:** Best-effort parsing, not critical for v1

### 5. Interactive Tasks
- Should we support interactive Claude Code sessions?
- Multi-turn conversations via Slack?

**Proposal:** Not for v1, stick to one-shot tasks

## Benefits of This Design

1. **No API Costs** - Uses Claude Code CLI, no direct API billing
2. **Better Isolation** - Each task has own workspace, no conflicts
3. **Simpler Code** - No custom tool implementation needed
4. **True Parallelism** - Tasks can run truly in parallel without file conflicts
5. **Debugging** - Can inspect workspace after task completion
6. **Flexibility** - Claude Code handles tool use, we just provide environment

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Claude Code not installed | High | Validate on startup, clear error message |
| Workspace disk usage | Medium | Auto-cleanup for random tasks, periodic archival |
| Process management | Medium | Use subprocess timeouts, proper cleanup |
| Git conflicts | Low | Isolated repos per task |
| Performance | Low | Monitor workspace creation overhead |

## Success Criteria

- ✓ All existing Slack commands work
- ✓ Random thoughts auto-commit to random-ideas branch
- ✓ Serious tasks create PRs with proper validation
- ✓ Parallel execution works without conflicts
- ✓ Workspaces are properly isolated
- ✓ No API key required
- ✓ Documentation updated

## Next Steps

1. Review this design document
2. Get feedback on approach
3. Decide on any open questions
4. Begin Phase 1 implementation
5. Create feature branch for development
6. Test incrementally

---

**Document Version:** 1.0
**Date:** 2025-10-21
**Status:** DRAFT - Pending Review
