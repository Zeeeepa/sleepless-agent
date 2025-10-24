"""Shared helpers for task creation and metadata handling."""

from __future__ import annotations

import re
from typing import Optional, Tuple


def slugify_project(identifier: str) -> str:
    """Convert project name/id to Kebab-case slug used as project_id."""
    return re.sub(r"[^a-z0-9-]", "-", identifier.lower()).strip("-")


def parse_task_description(description: str) -> Tuple[str, Optional[str], Optional[str]]:
    """Normalize task description, extracting optional project flag and notes.

    Returns:
        tuple of (clean_description, project_name, note)
    """
    note: Optional[str] = None
    working = description.strip()
    project_name: Optional[str] = None

    # Extract --project= flag if present
    project_match = re.search(r"--project=(\S+)", working)
    if project_match:
        project_name = project_match.group(1)
        working = working.replace(project_match.group(0), "").strip()

    # Handle legacy flags
    if "--serious" in working:
        working = working.replace("--serious", "").strip()
        note = "ℹ️ `--serious` flag no longer needed; `/task` and CLI tasks are serious by default."

    if "--random" in working:
        working = working.replace("--random", "").strip()
        warning = (
            "ℹ️ Random thoughts belong in `/think`. Treating this as a serious task."
        )
        note = f"{note}\n{warning}" if note else warning

    return working, project_name, note

