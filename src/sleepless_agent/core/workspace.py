"""Interactive workspace setup utilities."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from loguru import logger


@dataclass
class WorkspaceConfigResult:
    workspace_root: Path
    use_remote_repo: bool
    remote_repo_url: Optional[str]


class WorkspaceSetup:
    """Handle first-run setup for workspace configuration."""

    def __init__(self, agent_config):
        self.agent_config = agent_config
        self.state_path = Path.home() / ".sleepless_agent_setup.json"
        self.default_workspace = agent_config.workspace_root.expanduser().resolve()

    def run(self) -> WorkspaceConfigResult:
        """Load previous setup or prompt the user, then apply to config."""
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

        use_remote_input = input("Use remote GitHub repo to track? [y/N]: ").strip().lower()
        use_remote_repo = use_remote_input in {"y", "yes"}

        remote_repo_url = None
        if use_remote_repo:
            default_remote = "git@github.com:username/sleepless-agent.git"
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
