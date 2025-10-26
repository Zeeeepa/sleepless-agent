"""Result storage and git integration."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from sleepless_agent.monitoring.logging import get_logger
from sleepless_agent.storage.sqlite import SQLiteStore
from sleepless_agent.core.models import Result

logger = get_logger(__name__)


class ResultManager(SQLiteStore):
    """Manages task results and storage."""

    def __init__(self, db_path: str, results_path: str):
        super().__init__(db_path)
        self.results_path = Path(results_path)
        self.results_path.mkdir(parents=True, exist_ok=True)

    def _write_result_file(self, result: Result) -> Path:
        """Persist result data to JSON file and return its path."""
        result_file = self.results_path / f"task_{result.task_id}_{result.id}.json"
        try:
            payload = {
                "task_id": result.task_id,
                "result_id": result.id,
                "created_at": result.created_at.isoformat() if result.created_at else None,
                "output": result.output,
                "files_modified": json.loads(result.files_modified) if result.files_modified else None,
                "commands_executed": json.loads(result.commands_executed) if result.commands_executed else None,
                "processing_time_seconds": result.processing_time_seconds,
                "git_commit_sha": result.git_commit_sha,
                "git_pr_url": result.git_pr_url,
                "git_branch": result.git_branch,
                "workspace_path": result.workspace_path,
            }
            result_file.write_text(json.dumps(payload, indent=2))
        except Exception as exc:
            logger.error(f"Failed to write result file {result_file}: {exc}")
            raise
        return result_file

    def save_result(
        self,
        task_id: int,
        output: str,
        files_modified: Optional[list] = None,
        commands_executed: Optional[list] = None,
        processing_time_seconds: Optional[int] = None,
        git_commit_sha: Optional[str] = None,
        git_pr_url: Optional[str] = None,
        git_branch: Optional[str] = None,
        workspace_path: Optional[str] = None,
    ) -> Result:
        """Save task result to database and file."""

        def _op(session: Session) -> Result:
            result = Result(
                task_id=task_id,
                output=output,
                files_modified=json.dumps(files_modified) if files_modified else None,
                commands_executed=json.dumps(commands_executed) if commands_executed else None,
                processing_time_seconds=processing_time_seconds,
                git_commit_sha=git_commit_sha,
                git_pr_url=git_pr_url,
                git_branch=git_branch,
                workspace_path=workspace_path,
            )
            session.add(result)
            session.flush()
            result_file = self._write_result_file(result)
            logger.debug(f"Result saved for task {task_id}: {result_file}")
            return result

        try:
            return self._run_write(_op)
        except Exception as exc:
            logger.error(f"Failed to save result: {exc}")
            raise

    def get_result(self, result_id: int) -> Optional[Result]:
        """Get result by ID."""

        def _op(session: Session) -> Optional[Result]:
            return session.query(Result).filter(Result.id == result_id).first()

        return self._run_read(_op)

    def get_task_results(self, task_id: int) -> list[Result]:
        """Get all results for a task."""

        def _op(session: Session) -> list[Result]:
            return session.query(Result).filter(Result.task_id == task_id).all()

        return self._run_read(_op)

    def update_result_commit_info(
        self,
        result_id: int,
        git_commit_sha: Optional[str],
        git_pr_url: Optional[str] = None,
        git_branch: Optional[str] = None,
    ) -> Optional[Path]:
        """Update git commit information for a result record."""

        def _op(session: Session) -> Optional[Path]:
            result = session.query(Result).filter(Result.id == result_id).first()
            if not result:
                logger.warning(f"Result {result_id} not found for commit update")
                return None

            result.git_commit_sha = git_commit_sha
            result.git_pr_url = git_pr_url
            result.git_branch = git_branch
            return self.results_path / f"task_{result.task_id}_{result.id}.json"

        updated_path = self._run_write(_op)
        return updated_path
