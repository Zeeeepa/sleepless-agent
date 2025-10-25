"""Backward-compatible storage exports."""

from sleepless_agent.workspaces.git import GitManager
from sleepless_agent.persistence.results import ResultManager

__all__ = ["ResultManager", "GitManager"]
