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

    def __init__(self, workspace: str, random_ideas_branch: str = "random-ideas"):
        """Initialize git manager"""
        self.workspace = Path(workspace)
        self.random_ideas_branch = random_ideas_branch
        self.original_branch = None

    def init_repo(self) -> bool:
        """Initialize git repo if not already initialized"""
        try:
            if not (self.workspace / ".git").exists():
                self._run_git("init")
                self._run_git("config", "user.email", "agent@sleepless.local")
                self._run_git("config", "user.name", "Sleepless Agent")
                logger.info("Initialized git repo")
                return True
            return True
        except Exception as e:
            logger.error(f"Failed to init git repo: {e}")
            return False

    def create_random_ideas_branch(self) -> bool:
        """Create random-ideas branch if it doesn't exist"""
        try:
            branches = self._run_git("branch", "-a")
            if self.random_ideas_branch not in branches:
                self._run_git("checkout", "-b", self.random_ideas_branch)
                self._run_git("checkout", "-")  # Switch back to original
                logger.info(f"Created {self.random_ideas_branch} branch")
            return True
        except Exception as e:
            logger.error(f"Failed to create random-ideas branch: {e}")
            return False

    def commit_random_thought(
        self,
        task_id: int,
        description: str,
        result_content: str,
    ) -> Optional[str]:
        """Commit a random thought to random-ideas branch"""
        try:
            # Save original branch
            self.original_branch = self._run_git("rev-parse", "--abbrev-ref", "HEAD").strip()

            # Switch to random-ideas branch
            self._run_git("checkout", self.random_ideas_branch)

            # Create result file
            timestamp = datetime.utcnow().isoformat()
            filename = f"idea_{task_id}_{timestamp.replace(':', '-')}.md"
            file_path = self.workspace / filename

            content = f"""# Task #{task_id}: {description}

**Date**: {timestamp}

## Result

{result_content}
"""
            file_path.write_text(content)

            # Commit
            self._run_git("add", filename)
            commit_msg = f"[Random] Task #{task_id}: {description[:50]}"
            commit_hash = self._run_git("commit", "-m", commit_msg).strip()

            logger.info(f"Committed random thought: {commit_hash}")

            # Switch back
            if self.original_branch:
                self._run_git("checkout", self.original_branch)

            return commit_hash

        except Exception as e:
            logger.error(f"Failed to commit random thought: {e}")
            try:
                if self.original_branch:
                    self._run_git("checkout", self.original_branch)
            except:
                pass
            return None

    def create_task_branch(self, task_id: int, task_description: str) -> str:
        """Create feature branch for serious task"""
        try:
            branch_name = f"task/{task_id}-{task_description[:30].lower().replace(' ', '-')}"
            branch_name = "".join(c for c in branch_name if c.isalnum() or c in "-_/")[:50]

            self._run_git("checkout", "-b", branch_name)
            logger.info(f"Created task branch: {branch_name}")
            return branch_name

        except Exception as e:
            logger.error(f"Failed to create task branch: {e}")
            return ""

    def commit_task_changes(
        self,
        task_id: int,
        files: List[str],
        message: str,
    ) -> Optional[str]:
        """Commit task changes"""
        try:
            # Stage files
            for file in files:
                self._run_git("add", file)

            # Commit
            full_message = f"[Task #{task_id}] {message}"
            commit_hash = self._run_git("commit", "-m", full_message).strip()

            logger.info(f"Committed task changes: {commit_hash}")
            return commit_hash

        except Exception as e:
            logger.error(f"Failed to commit task changes: {e}")
            return None

    def create_pr(
        self,
        task_id: int,
        task_description: str,
        branch: str,
        base_branch: str = "main",
    ) -> Optional[str]:
        """Create pull request using gh CLI"""
        try:
            # Check if gh is available
            self._run_command("gh", "--version")

            title = f"[Task #{task_id}] {task_description[:60]}"
            body = f"""## Task #{task_id}

### Description
{task_description}

### Changes
This PR contains automated changes from Sleepless Agent.

### What to review
- [ ] Code changes are correct
- [ ] Tests pass
- [ ] No breaking changes

---
*Generated by Sleepless Agent*
"""

            # Create PR
            result = self._run_command(
                "gh", "pr", "create",
                "--title", title,
                "--body", body,
                "--base", base_branch,
                "--head", branch,
            )

            logger.info(f"Created PR: {result}")
            return result.strip()

        except Exception as e:
            logger.error(f"Failed to create PR: {e}")
            return None

    def get_current_branch(self) -> str:
        """Get current branch name"""
        try:
            return self._run_git("rev-parse", "--abbrev-ref", "HEAD").strip()
        except:
            return "main"

    def get_status(self) -> dict:
        """Get git status"""
        try:
            status = self._run_git("status", "--porcelain")
            branch = self.get_current_branch()

            return {
                "branch": branch,
                "dirty": bool(status.strip()),
                "status": status,
            }
        except Exception as e:
            logger.error(f"Failed to get git status: {e}")
            return {}

    def is_repo(self) -> bool:
        """Check if directory is a git repo"""
        return (self.workspace / ".git").exists()

    def has_changes(self) -> bool:
        """Check if there are uncommitted changes"""
        try:
            status = self._run_git("status", "--porcelain")
            return bool(status.strip())
        except:
            return False

    def _run_git(self, *args) -> str:
        """Run git command in workspace"""
        return self._run_command("git", *args)

    def _run_command(self, *args, timeout: int = 30) -> str:
        """Run command in workspace"""
        try:
            result = subprocess.run(
                args,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            if result.returncode != 0:
                raise RuntimeError(f"Command failed: {result.stderr}")

            return result.stdout

        except Exception as e:
            logger.error(f"Command failed: {' '.join(args)}: {e}")
            raise

    def validate_changes(self, files: List[str]) -> Tuple[bool, str]:
        """Validate changes before committing"""
        issues = []

        for file in files:
            file_path = self.workspace / file

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
