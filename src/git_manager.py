"""Git integration for auto-commits and PR creation"""

import json
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


class GitManager:
    """Manages git operations for task results"""

    def __init__(self, workspace_root: str, random_ideas_branch: str = "random-ideas"):
        """Initialize git manager

        Args:
            workspace_root: Root directory containing isolated task workspaces
            random_ideas_branch: Branch name for random thoughts
        """
        self.workspace_root = Path(workspace_root)
        self.main_repo = Path.cwd()  # The sleepless-agent repo itself
        self.random_ideas_branch = random_ideas_branch
        self.original_branch = None

    def init_repo(self) -> bool:
        """Initialize git repo in main repo if not already initialized"""
        try:
            if not (self.main_repo / ".git").exists():
                self._run_git_in_repo(self.main_repo, "init")
                self._run_git_in_repo(self.main_repo, "config", "user.email", "agent@sleepless.local")
                self._run_git_in_repo(self.main_repo, "config", "user.name", "Sleepless Agent")
                logger.info("Initialized git repo in main repo")
                return True
            return True
        except Exception as e:
            logger.error(f"Failed to init git repo: {e}")
            return False

    def create_random_ideas_branch(self) -> bool:
        """Create random-ideas branch in main repo if it doesn't exist"""
        try:
            branches = self._run_git_in_repo(self.main_repo, "branch", "-a")
            if self.random_ideas_branch not in branches:
                self._run_git_in_repo(self.main_repo, "checkout", "-b", self.random_ideas_branch)
                self._run_git_in_repo(self.main_repo, "checkout", "-")  # Switch back to original
                logger.info(f"Created {self.random_ideas_branch} branch in main repo")
            return True
        except Exception as e:
            logger.error(f"Failed to create random-ideas branch: {e}")
            return False

    def commit_random_thought(
        self,
        task_id: int,
        task_workspace: Path,
        description: str,
        result_content: str,
    ) -> Optional[str]:
        """Commit a random thought from task workspace to random-ideas branch in main repo

        Args:
            task_id: Task ID
            task_workspace: Path to task's isolated workspace
            description: Task description
            result_content: Result output from Claude Code

        Returns:
            Commit SHA if successful, None otherwise
        """
        try:
            # Save original branch
            self.original_branch = self._run_git_in_repo(
                self.main_repo, "rev-parse", "--abbrev-ref", "HEAD"
            ).strip()

            # Switch to random-ideas branch
            self._run_git_in_repo(self.main_repo, "checkout", self.random_ideas_branch)

            # Create result file in main repo
            timestamp = datetime.utcnow().isoformat()
            filename = f"idea_{task_id}_{timestamp.replace(':', '-')}.md"
            file_path = self.main_repo / filename

            content = f"""# Task #{task_id}: {description}

**Date**: {timestamp}
**Workspace**: {task_workspace}

## Result

{result_content}
"""
            file_path.write_text(content)

            # Commit
            self._run_git_in_repo(self.main_repo, "add", filename)
            commit_msg = f"[Random] Task #{task_id}: {description[:50]}"
            commit_result = self._run_git_in_repo(self.main_repo, "commit", "-m", commit_msg)

            # Extract commit hash
            commit_hash = self._run_git_in_repo(self.main_repo, "rev-parse", "HEAD").strip()

            logger.info(f"Committed random thought to main repo: {commit_hash}")

            # Switch back
            if self.original_branch:
                self._run_git_in_repo(self.main_repo, "checkout", self.original_branch)

            return commit_hash

        except Exception as e:
            logger.error(f"Failed to commit random thought: {e}")
            try:
                if self.original_branch:
                    self._run_git_in_repo(self.main_repo, "checkout", self.original_branch)
            except:
                pass
            return None

    def commit_in_workspace(
        self,
        workspace: Path,
        files: List[str],
        message: str,
    ) -> Optional[str]:
        """Commit changes within an isolated task workspace

        Args:
            workspace: Path to task workspace
            files: List of file paths (relative to workspace) to commit
            message: Commit message

        Returns:
            Commit SHA if successful, None otherwise
        """
        try:
            # Stage files
            for file in files:
                self._run_git_in_repo(workspace, "add", file)

            # Commit
            self._run_git_in_repo(workspace, "commit", "-m", message)

            # Get commit hash
            commit_hash = self._run_git_in_repo(workspace, "rev-parse", "HEAD").strip()

            logger.info(f"Committed changes in workspace {workspace}: {commit_hash}")
            return commit_hash

        except Exception as e:
            logger.error(f"Failed to commit in workspace: {e}")
            return None

    def create_pr_from_workspace(
        self,
        task_workspace: Path,
        task_id: int,
        task_description: str,
        branch: str,
        base_branch: str = "main",
    ) -> Optional[str]:
        """Create PR from isolated workspace by pushing to remote

        Args:
            task_workspace: Path to task workspace
            task_id: Task ID
            task_description: Task description
            branch: Branch name to push
            base_branch: Base branch for PR

        Returns:
            PR URL if successful, None otherwise
        """
        try:
            # Check if gh is available
            self._run_command_in_repo(task_workspace, "gh", "--version")

            # Push branch to remote
            # Note: This assumes the workspace git is connected to a remote
            # For now, we'll skip actual push and just log
            logger.warning(
                f"PR creation from workspace not fully implemented yet. "
                f"Workspace: {task_workspace}, branch: {branch}"
            )

            title = f"[Task #{task_id}] {task_description[:60]}"
            body = f"""## Task #{task_id}

### Description
{task_description}

### Changes
This PR contains automated changes from Sleepless Agent (Claude Code).

### What to review
- [ ] Code changes are correct
- [ ] Tests pass
- [ ] No breaking changes

---
*Generated by Sleepless Agent with Claude Code*
"""

            # Create PR
            # TODO: Implement actual PR creation from workspace
            # This requires setting up remote in workspace and pushing
            logger.info(f"Would create PR: {title}")
            return None

        except Exception as e:
            logger.error(f"Failed to create PR from workspace: {e}")
            return None

    def get_current_branch(self, repo: Optional[Path] = None) -> str:
        """Get current branch name

        Args:
            repo: Repository path (default: main_repo)

        Returns:
            Current branch name
        """
        repo = repo or self.main_repo
        try:
            return self._run_git_in_repo(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
        except:
            return "main"

    def get_status(self, repo: Optional[Path] = None) -> dict:
        """Get git status

        Args:
            repo: Repository path (default: main_repo)

        Returns:
            Dict with branch, dirty status, and status output
        """
        repo = repo or self.main_repo
        try:
            status = self._run_git_in_repo(repo, "status", "--porcelain")
            branch = self.get_current_branch(repo)

            return {
                "branch": branch,
                "dirty": bool(status.strip()),
                "status": status,
            }
        except Exception as e:
            logger.error(f"Failed to get git status: {e}")
            return {}

    def is_repo(self, repo: Optional[Path] = None) -> bool:
        """Check if directory is a git repo

        Args:
            repo: Repository path (default: main_repo)

        Returns:
            True if directory is a git repo
        """
        repo = repo or self.main_repo
        return (repo / ".git").exists()

    def has_changes(self, repo: Optional[Path] = None) -> bool:
        """Check if there are uncommitted changes

        Args:
            repo: Repository path (default: main_repo)

        Returns:
            True if there are uncommitted changes
        """
        repo = repo or self.main_repo
        try:
            status = self._run_git_in_repo(repo, "status", "--porcelain")
            return bool(status.strip())
        except:
            return False

    def _run_git_in_repo(self, repo: Path, *args) -> str:
        """Run git command in specific repository

        Args:
            repo: Repository path
            *args: Git command arguments

        Returns:
            Command stdout
        """
        return self._run_command_in_repo(repo, "git", *args)

    def _run_command_in_repo(self, repo: Path, *args, timeout: int = 30) -> str:
        """Run command in specific repository

        Args:
            repo: Repository path
            *args: Command and arguments
            timeout: Command timeout in seconds

        Returns:
            Command stdout
        """
        try:
            result = subprocess.run(
                args,
                cwd=repo,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            if result.returncode != 0:
                raise RuntimeError(f"Command failed: {result.stderr}")

            return result.stdout

        except Exception as e:
            logger.error(f"Command failed in {repo}: {' '.join(args)}: {e}")
            raise

    def validate_changes(self, workspace: Path, files: List[str]) -> Tuple[bool, str]:
        """Validate changes before committing

        Args:
            workspace: Workspace path
            files: List of files to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        issues = []

        for file in files:
            file_path = workspace / file

            # Check for secrets
            if self._contains_secrets(file_path):
                issues.append(f"Potential secret in {file}")

            # Check for syntax errors
            if file.endswith(".py"):
                if not self._validate_python_syntax(file_path):
                    issues.append(f"Python syntax error in {file}")

        if issues:
            return False, "\n".join(issues)

        return True, "OK"

    def _contains_secrets(self, file_path: Path) -> bool:
        """Check if file contains potential secrets"""
        secret_patterns = [
            "PRIVATE_KEY",
            "API_KEY",
            "PASSWORD",
            "SECRET",
            "TOKEN",
            "credential",
        ]

        try:
            content = file_path.read_text()
            for pattern in secret_patterns:
                if pattern in content.upper():
                    return True
        except:
            pass

        return False

    def _validate_python_syntax(self, file_path: Path) -> bool:
        """Validate Python file syntax"""
        try:
            import ast
            content = file_path.read_text()
            ast.parse(content)
            return True
        except:
            return False
