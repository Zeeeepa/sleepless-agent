"""Interactive workspace setup utilities."""

from __future__ import annotations

import json
from dataclasses import dataclass
import subprocess
from pathlib import Path
from typing import Optional

from sleepless_agent.monitoring.logging import get_logger
logger = get_logger(__name__)


@dataclass
class WorkspaceConfigResult:
    workspace_root: Path
    use_remote_repo: bool
    remote_repo_url: Optional[str]


class WorkspaceSetup:
    """Handle first-run setup for workspace configuration."""

    def __init__(self, agent_config, git_config=None):
        self.agent_config = agent_config
        self.git_config = git_config  # git config from config.yaml
        self.state_path = Path.home() / ".sleepless_agent_setup.json"
        self.default_workspace = agent_config.workspace_root.expanduser().resolve()
        self.repo_root = Path.cwd()
        self.default_remote_url = self._detect_default_remote_url()

    def run(self) -> WorkspaceConfigResult:
        """Load configuration from config.yaml first, then fall back to JSON file or prompts."""
        # First priority: config.yaml git section
        if self.git_config:
            use_remote_repo = bool(self.git_config.get("use_remote_repo", False))
            remote_repo_url = self.git_config.get("remote_repo_url")
            workspace_root = self.default_workspace

            logger.info("Using git configuration from config.yaml")
        else:
            # Fall back to JSON file or prompts
            data = self._load_state()
            if not data:
                data = self._prompt_user()
                self._save_state(data)

            workspace_root = Path(data.get("workspace_root", self.default_workspace)).expanduser().resolve()
            use_remote_repo = bool(data.get("use_remote_repo", False))
            remote_repo_url = data.get("remote_repo_url")

        self._apply_workspace_root(workspace_root)

        return WorkspaceConfigResult(
            workspace_root=workspace_root,
            use_remote_repo=use_remote_repo,
            remote_repo_url=remote_repo_url,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load_state(self) -> dict:
        if not self.state_path.exists():
            return {}
        try:
            return json.loads(self.state_path.read_text())
        except Exception as exc:
            logger.warning(f"Failed to parse setup file {self.state_path}: {exc}")
            return {}

    def _save_state(self, data: dict):
        try:
            self.state_path.write_text(json.dumps(data, indent=2))
            logger.info(f"Saved setup configuration to {self.state_path}")
        except Exception as exc:
            logger.warning(f"Failed to write setup file {self.state_path}: {exc}")

    def _prompt_user(self) -> dict:
        print("\nWelcome to Sleepless Agent! Let's finish the initial setup.")
        workspace_input = input(f"Workspace root [{self.default_workspace}]: ").strip()
        workspace_root = (
            Path(workspace_input).expanduser().resolve() if workspace_input else self.default_workspace
        )

        use_remote_input = input("Use remote GitHub repo to track? [Y/n]: ").strip().lower()
        use_remote_repo = use_remote_input not in {"n", "no"}

        remote_repo_url = None
        if use_remote_repo:
            default_remote = self.default_remote_url or self._fallback_remote_url()
            remote_repo_input = input(f"Remote repository URL [{default_remote}]: ").strip()
            remote_repo_url = remote_repo_input or default_remote

        return {
            "workspace_root": str(workspace_root),
            "use_remote_repo": use_remote_repo,
            "remote_repo_url": remote_repo_url,
        }

    def _apply_workspace_root(self, workspace_root: Path):
        """Update config paths to reflect new workspace root."""
        data_dir = workspace_root / "data"
        self.agent_config.workspace_root = workspace_root
        self.agent_config.shared_workspace = workspace_root / "shared"
        self.agent_config.db_path = data_dir / "tasks.db"
        self.agent_config.results_path = data_dir / "results"

    # ------------------------------------------------------------------
    # Git helpers
    # ------------------------------------------------------------------
    def _detect_default_remote_url(self) -> Optional[str]:
        """Attempt to infer a sane default remote URL."""
        origin_url = self._run_git_command(["git", "remote", "get-url", "origin"])
        if origin_url:
            return origin_url.strip()

        username = self._get_git_identity()
        if not username:
            return None

        repo_name = self.repo_root.name or "sleepless-agent"
        user_slug = username.replace(" ", "-")
        return f"git@github.com:{user_slug}/{repo_name}.git"

    def _get_git_identity(self) -> Optional[str]:
        """Get git user identity, preferring user.name over user.email."""
        name = self._run_git_command(["git", "config", "--get", "user.name"])
        if name:
            return name.strip()

        email = self._run_git_command(["git", "config", "--get", "user.email"])
        if email:
            return email.strip().split("@")[0]

        return None

    def _run_git_command(self, cmd: list[str]) -> Optional[str]:
        """Execute git command in repository root and return stdout."""
        try:
            result = subprocess.run(
                cmd,
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception as exc:  # pragma: no cover - best effort
            logger.debug(f"Failed to run {' '.join(cmd)}: {exc}")
        return None

    def _fallback_remote_url(self) -> str:
        repo_name = self.repo_root.name or "sleepless-agent"
        return f"git@github.com:username/{repo_name}.git"