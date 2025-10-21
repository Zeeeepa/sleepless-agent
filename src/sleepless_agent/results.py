"""Result storage and git integration"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sleepless_agent.models import Result

logger = logging.getLogger(__name__)


class ResultManager:
    """Manages task results and storage"""

    def __init__(self, db_path: str, results_path: str):
        """Initialize result manager"""
        self.db_path = db_path
        self.results_path = Path(results_path)
        self.results_path.mkdir(parents=True, exist_ok=True)

        self.engine = create_engine(f"sqlite:///{db_path}", echo=False, future=True)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)

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
        session = self.SessionLocal()
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
            session.commit()

            # Save to file
            result_file = self.results_path / f"task_{task_id}_{result.id}.json"
            result_file.write_text(
                json.dumps(
                    {
                        "task_id": task_id,
                        "result_id": result.id,
                        "created_at": result.created_at.isoformat(),
                        "output": output,
                        "files_modified": files_modified,
                        "commands_executed": commands_executed,
                        "processing_time_seconds": processing_time_seconds,
                        "git_commit_sha": git_commit_sha,
                        "git_pr_url": git_pr_url,
                        "git_branch": git_branch,
                        "workspace_path": workspace_path,
                    },
                    indent=2,
                )
            )

            logger.info(f"Result saved for task {task_id}: {result_file}")
            return result

        except Exception as e:
            session.rollback()
            logger.error(f"Failed to save result: {e}")
            raise
        finally:
            session.close()

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
