"""Result storage and git integration"""

import json
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, TypeVar

from loguru import logger
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.exc import OperationalError

from sleepless_agent.core.models import Result

T = TypeVar("T")


class ResultManager:
    """Manages task results and storage"""

    def __init__(self, db_path: str, results_path: str):
        """Initialize result manager"""
        self.db_path = db_path
        self.results_path = Path(results_path)
        self.results_path.mkdir(parents=True, exist_ok=True)

        self._create_engine()

    def _create_engine(self):
        self.engine = create_engine(f"sqlite:///{self.db_path}", echo=False, future=True)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)

    def _reset_engine(self):
        self.engine.dispose(close=True)
        self._create_engine()

    @staticmethod
    def _should_reset_on_error(exc: OperationalError) -> bool:
        message = str(exc).lower()
        return "readonly" in message or ("sqlite" in message and "locked" in message)

    def _execute_with_retry(self, operation: Callable[[Session], T]) -> T:
        for attempt in range(2):
            session = self.SessionLocal()
            try:
                return operation(session)
            except OperationalError as exc:
                session.rollback()
                if self._should_reset_on_error(exc) and attempt == 0:
                    logger.warning(
                        "SQLite engine reported a read-only state; reinitializing connection."
                    )
                    self._reset_engine()
                    continue
                raise
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
        raise RuntimeError("Failed to execute database operation after retries.")

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
        """Save task result to database and file"""
        def operation(session):
            try:
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

                session.commit()
                logger.info(f"Result saved for task {task_id}: {result_file}")
                return result
            except Exception:
                session.rollback()
                raise

        try:
            return self._execute_with_retry(operation)
        except Exception as e:
            logger.error(f"Failed to save result: {e}")
            raise

    def get_result(self, result_id: int) -> Optional[Result]:
        """Get result by ID"""
        session = self.SessionLocal()
        try:
            result = session.query(Result).filter(Result.id == result_id).first()
            return result
        finally:
            session.close()

    def get_task_results(self, task_id: int) -> list:
        """Get all results for a task"""
        session = self.SessionLocal()
        try:
            results = session.query(Result).filter(Result.task_id == task_id).all()
            return results
        finally:
            session.close()

    def save_result_file(self, task_id: int, filename: str, content: str):
        """Save result output to file"""
        task_dir = self.results_path / f"task_{task_id}"
        task_dir.mkdir(parents=True, exist_ok=True)
        file_path = task_dir / filename
        file_path.write_text(content)
        logger.info(f"Result file saved: {file_path}")

    def get_result_files(self, task_id: int) -> list:
        """Get all result files for a task"""
        task_dir = self.results_path / f"task_{task_id}"
        if not task_dir.exists():
            return []
        return list(task_dir.glob("*"))

    def cleanup_result_files(self, task_id: int, keep_days: int = 30):
        """Cleanup old result files"""
        task_dir = self.results_path / f"task_{task_id}"
        if not task_dir.exists():
            return

        import time
        now = time.time()
        for file_path in task_dir.glob("*"):
            age_days = (now - file_path.stat().st_mtime) / 86400
            if age_days > keep_days:
                file_path.unlink()
                logger.info(f"Deleted old result file: {file_path}")

    def update_result_commit_info(
        self,
        result_id: int,
        git_commit_sha: Optional[str],
        git_pr_url: Optional[str] = None,
        git_branch: Optional[str] = None,
    ) -> Optional[Path]:
        """Update git commit information for a result record."""
        def operation(session):
            try:
                result = session.query(Result).filter(Result.id == result_id).first()
                if not result:
                    logger.warning(f"Result {result_id} not found for commit update")
                    return None

                result.git_commit_sha = git_commit_sha
                result.git_pr_url = git_pr_url
                result.git_branch = git_branch
                session.commit()

                return self.results_path / f"task_{result.task_id}_{result.id}.json"
            except Exception:
                session.rollback()
                raise

        try:
            return self._execute_with_retry(operation)
        except Exception as exc:
            logger.error(f"Failed to update commit info for result {result_id}: {exc}")
            return None
