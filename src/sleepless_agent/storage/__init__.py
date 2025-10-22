"""Data persistence and integration - Results and Git operations"""

from .git_manager import GitManager
from .results import ResultManager

__all__ = ["ResultManager", "GitManager"]
