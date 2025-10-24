"""Main agent daemon - runs continuously"""

import asyncio
import os
import signal
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Set, List

from loguru import logger

from sleepless_agent.interfaces.bot import SlackBot
from sleepless_agent.execution.claude_code_executor import ClaudeCodeExecutor
from sleepless_agent.config import get_config
from sleepless_agent.storage.git_manager import GitManager
from sleepless_agent.core.models import TaskPriority, init_db
from sleepless_agent.monitoring.monitor import HealthMonitor, PerformanceLogger
from sleepless_agent.monitoring.report_generator import ReportGenerator, TaskMetrics
from sleepless_agent.storage.results import ResultManager
from sleepless_agent.core.scheduler import SmartScheduler, BudgetManager
from sleepless_agent.core.task_queue import TaskQueue
from sleepless_agent.core.auto_generator import AutoTaskGenerator
from sleepless_agent.core.workspace import WorkspaceSetup
from sleepless_agent.core.live_status import LiveStatusTracker

# Setup loguru
logger.remove()  # Remove default handler
logger.add(sys.stderr, format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}", level="INFO")


class SleepleassAgent:
    """Main sleepless agent daemon"""

    def __init__(self):
        """Initialize agent"""
        self.config = get_config()
        self.running = False
        self.last_daily_summarization = None  # Track last summarization time
        setup = WorkspaceSetup(self.config.agent)
        setup_result = setup.run()
        self.use_remote_repo = setup_result.use_remote_repo
        self.remote_repo_url = setup_result.remote_repo_url

        # Initialize components
        self._init_directories()
        engine = init_db(str(self.config.agent.db_path))
        self.task_queue = TaskQueue(str(self.config.agent.db_path))

        live_status_path = Path(self.config.agent.db_path).parent / "live_status.json"
        self.live_status_tracker = LiveStatusTracker(live_status_path)
        self.live_status_tracker.clear_all()

        # Create session for budget manager and auto-generator
        from sqlalchemy.orm import sessionmaker
        Session = sessionmaker(bind=engine)
        self.db_session = Session()

        self.budget_manager = BudgetManager(
            session=self.db_session,
            daily_budget_usd=10.0,  # TODO: make configurable
            night_quota_percent=90.0,  # 90% for night, 10% for day
        )

        self.scheduler = SmartScheduler(
            task_queue=self.task_queue,
            max_parallel_tasks=self.config.agent.max_parallel_tasks,
            daily_budget_usd=10.0,  # TODO: make configurable
            night_quota_percent=90.0,  # 90% for night, 10% for day
            use_live_usage_check=self.config.multi_agent_workflow.pro_plan_monitoring.enabled,
            usage_command=self.config.multi_agent_workflow.pro_plan_monitoring.usage_command,
            pause_threshold_percent=self.config.multi_agent_workflow.pro_plan_monitoring.pause_threshold,
        )

        self.auto_generator = AutoTaskGenerator(
            db_session=self.db_session,
            config=self.config.auto_generation,
            budget_manager=self.budget_manager,
            workspace_root=self.config.agent.workspace_root,
        )
        self.claude = ClaudeCodeExecutor(
            workspace_root=str(self.config.agent.workspace_root),
            default_timeout=self.config.claude_code.default_timeout,
            live_status_tracker=self.live_status_tracker,
        )
        self.results = ResultManager(
            str(self.config.agent.db_path),
            str(self.config.agent.results_path),
        )
        self.git = GitManager(workspace_root=str(self.config.agent.workspace_root))
        self.git.init_repo()
        if self.use_remote_repo and self.remote_repo_url:
            try:
                self.git.configure_remote(self.remote_repo_url)
            except Exception as exc:
                logger.error(f"Failed to configure remote repository: {exc}")

        self.monitor = HealthMonitor(
            db_path=str(self.config.agent.db_path),
            results_path=str(self.config.agent.results_path),
        )
        self.perf_logger = PerformanceLogger(log_dir=str(self.config.agent.db_path.parent))
        self.report_generator = ReportGenerator(base_path=str(self.config.agent.db_path.parent / "reports"))

        self.bot = SlackBot(
            bot_token=self.config.slack.bot_token,
            app_token=self.config.slack.app_token,
            task_queue=self.task_queue,
            scheduler=self.scheduler,
            monitor=self.monitor,
            report_generator=self.report_generator,
            live_status_tracker=self.live_status_tracker,
        )

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _init_directories(self):
        """Initialize required directories"""
        self.config.agent.workspace_root.mkdir(parents=True, exist_ok=True)
        self.config.agent.shared_workspace.mkdir(parents=True, exist_ok=True)
        self.config.agent.results_path.mkdir(parents=True, exist_ok=True)
        self.config.agent.db_path.parent.mkdir(parents=True, exist_ok=True)

    def _signal_handler(self, sig, _frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {sig}, shutting down...")
        self.running = False
        if hasattr(self, "live_status_tracker"):
            self.live_status_tracker.clear_all()
        self.bot.stop()
        sys.exit(0)

    async def run(self):
        """Main agent loop"""
        self.running = True
        logger.info("Sleepless Agent starting...")

        # Start bot in background
        try:
            self.bot.start()
        except Exception as e:
            logger.error(f"Failed to start bot: {e}")
            return

        # Main event loop
        try:
            health_check_counter = 0
            while self.running:
                await self._process_tasks()

                # Check and generate tasks if usage is low
                try:
                    await self.auto_generator.check_and_generate()
                except Exception as e:
                    logger.error(f"Error in auto-generation: {e}")

                # Log health report every 60 seconds
                health_check_counter += 1
                if health_check_counter >= 12:  # 12 * 5 seconds = 60 seconds
                    self.monitor.log_health_report()
                    health_check_counter = 0

                # Daily report summarization at end of day (11:59 PM UTC)
                self._check_and_summarize_daily_reports()

                await asyncio.sleep(5)  # Check tasks every 5 seconds

        except KeyboardInterrupt:
            logger.info("Agent interrupted by user")
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}")
        finally:
            self.monitor.log_health_report()
            self.bot.stop()
            logger.info("Sleepless Agent stopped")

    def _enforce_task_timeouts(self):
        """Mark long-running tasks as timed out and record their failure."""
        timeout_seconds = self.config.agent.task_timeout_seconds
        if timeout_seconds <= 0:
            return

        timed_out_tasks = self.task_queue.timeout_expired_tasks(timeout_seconds)
        if not timed_out_tasks:
            return

        now = datetime.utcnow()
        for task in timed_out_tasks:
            started_at = task.started_at or now
            completed_at = task.completed_at or now
            elapsed_seconds = int((completed_at - started_at).total_seconds())
            elapsed_seconds = max(elapsed_seconds, timeout_seconds)
            timeout_message = task.error_message or f"Timed out after {elapsed_seconds // 60} minutes."

            cleanup_note = "workspace left in place"
            try:
                cleaned = self.claude.cleanup_workspace(task.id, force=False)
                if cleaned:
                    cleanup_note = "workspace cleaned"
            except Exception as exc:
                cleanup_note = "workspace cleanup failed"
                logger.debug(f"Failed to cleanup workspace for task {task.id}: {exc}")

            logger.warning(f"Task {task.id} timed out after {elapsed_seconds}s ({cleanup_note})")

            try:
                self.monitor.record_task_completion(elapsed_seconds, success=False)
            except Exception as exc:
                logger.debug(f"Failed to record timeout in health monitor for task {task.id}: {exc}")

            try:
                self.perf_logger.log_task_execution(
                    task_id=task.id,
                    description=task.description,
                    priority=task.priority.value if task.priority else "unknown",
                    duration_seconds=elapsed_seconds,
                    success=False,
                )
            except Exception as exc:
                logger.debug(f"Failed to log timeout metrics for task {task.id}: {exc}")

            try:
                task_metrics = TaskMetrics(
                    task_id=task.id,
                    description=task.description,
                    priority=task.priority.value if task.priority else "unknown",
                    status="failed",
                    duration_seconds=elapsed_seconds,
                    files_modified=0,
                    commands_executed=0,
                    error_message=timeout_message,
                )
                self.report_generator.append_task_completion(task_metrics, project_id=task.project_id)
            except Exception as exc:
                logger.debug(f"Failed to append timeout to report for task {task.id}: {exc}")

            if task.assigned_to and getattr(self, "bot", None):
                try:
                    minutes = max(1, elapsed_seconds // 60)
                    self.bot.send_message(
                        task.assigned_to,
                        f"⏱️ Task #{task.id} timed out after {minutes} minute(s). "
                        "It has been marked as failed.",
                    )
                except Exception as exc:
                    logger.debug(f"Failed to send timeout notification for task {task.id}: {exc}")

            if self.live_status_tracker:
                try:
                    self.live_status_tracker.clear(task.id)
                except Exception as exc:
                    logger.debug(f"Failed to clear live status for timed-out task {task.id}: {exc}")

    async def _process_tasks(self):
        """Process pending tasks using smart scheduler"""
        try:
            self._enforce_task_timeouts()
            # Get next tasks to execute
            tasks_to_execute = self.scheduler.get_next_tasks()

            for task in tasks_to_execute:
                if not self.running:
                    break

                await self._execute_task(task)
                self.scheduler.log_task_execution(task.id)
                await asyncio.sleep(1)  # Small delay between tasks

        except Exception as e:
            logger.error(f"Error in task processing loop: {e}")

    async def _execute_task(self, task):
        """Execute a single task"""
        separator = "=" * 72
        task_summary: Optional[str] = None
        try:
            # Mark as in progress
            self.task_queue.mark_in_progress(task.id)

            logger.info(separator)
            truncated_description = task.description
            if len(truncated_description) > 75:
                truncated_description = f"{truncated_description[:72]}..."
            logger.info(f"Starting task {task.id}: {truncated_description}")

            # Execute with Claude Code SDK (async)
            start_time = time.time()
            try:
                (
                    result_output,
                    files_modified,
                    commands_executed,
                    exit_code,
                    usage_metrics,
                ) = await asyncio.wait_for(
                    self.claude.execute_task(
                        task_id=task.id,
                        description=task.description,
                        task_type="general",
                        priority=task.priority.value,
                        timeout=self.config.agent.task_timeout_seconds,
                        project_id=task.project_id,
                        project_name=task.project_name,
                    ),
                    timeout=self.config.agent.task_timeout_seconds,
                )
            except asyncio.TimeoutError as exc:
                timeout_minutes = max(1, self.config.agent.task_timeout_seconds // 60)
                raise TimeoutError(
                    f"Timed out after {timeout_minutes} minute(s)"
                ) from exc
            processing_time = int(time.time() - start_time)

            files_modified = sorted(files_modified) if files_modified else []

            # Check if execution was successful
            if exit_code != 0:
                logger.warning(f"Task {task.id} completed with non-zero exit code: {exit_code}")
                # Note: We don't fail the task on non-zero exit, as Claude Code may still produce useful output

            # Handle git operations based on priority
            git_commit_sha = None
            git_pr_url = None
            git_branch = self.git.determine_branch(task.project_id)

            # Get task workspace
            task_workspace = self.claude.get_workspace_path(task.id, task.project_id)

            # Save result (commit info will be updated after git operations)
            result = self.results.save_result(
                task_id=task.id,
                output=result_output,
                files_modified=files_modified,
                commands_executed=commands_executed,
                processing_time_seconds=processing_time,
                git_commit_sha=git_commit_sha,
                git_pr_url=git_pr_url,
                git_branch=git_branch,
                workspace_path=str(task_workspace),
            )

            if task_workspace and task_workspace.exists():
                self.claude.cleanup_workspace_caches(task_workspace)
                files_for_commit: Set[str] = set(files_modified or [])

                if task.priority in (TaskPriority.RANDOM, TaskPriority.GENERATED):
                    if not files_for_commit:
                        summary_rel_path = self.git.write_summary_file(
                            workspace_path=task_workspace,
                            task_id=task.id,
                            priority=task.priority.value,
                            description=task.description,
                            result_output=result_output,
                        )
                        if summary_rel_path:
                            files_for_commit.add(summary_rel_path)
                    commit_targets = self._collect_commit_targets(task_workspace, files_for_commit)
                    if commit_targets:
                        commit_message = f"Capture thought: #{task.id} {task.description[:60]}"
                        git_commit_sha = self.git.commit_workspace_changes(
                            branch=git_branch,
                            workspace_path=task_workspace,
                            files=commit_targets,
                            message=commit_message,
                        )
                elif task.priority == TaskPriority.SERIOUS:
                    if files_for_commit:
                        is_valid, validation_msg = self.git.validate_changes(
                            task_workspace, sorted(files_for_commit)
                        )
                        if is_valid:
                            commit_targets = self._collect_commit_targets(task_workspace, files_for_commit)
                            if commit_targets:
                                commit_message = f"Implement task #{task.id}: {task.description[:60]}"
                                git_commit_sha = self.git.commit_workspace_changes(
                                    branch=git_branch,
                                    workspace_path=task_workspace,
                                    files=commit_targets,
                                    message=commit_message,
                                )
                        else:
                            logger.warning(f"Validation failed for task {task.id}: {validation_msg}")
                else:
                    commit_targets = self._collect_commit_targets(task_workspace, files_for_commit)
                    if commit_targets:
                        commit_message = f"Task #{task.id} update: {task.description[:60]}"
                        git_commit_sha = self.git.commit_workspace_changes(
                            branch=git_branch,
                            workspace_path=task_workspace,
                            files=commit_targets,
                            message=commit_message,
                        )

                if git_commit_sha:
                    self.results.update_result_commit_info(
                        result.id,
                        git_commit_sha=git_commit_sha,
                        git_pr_url=git_pr_url,
                        git_branch=git_branch,
                    )
                else:
                    logger.debug(f"No git commit produced for task {task.id}")
            else:
                logger.warning(f"No workspace found for task {task.id}; skipping git operations")

            # Mark as completed
            self.task_queue.mark_completed(task.id, result_id=result.id)

            # Record to daily report
            try:
                git_info = None
                if git_commit_sha or git_pr_url:
                    git_info = ""
                    if git_commit_sha:
                        git_info += f"Commit: {git_commit_sha[:8]}"
                    if git_pr_url:
                        git_info += f" PR: {git_pr_url}"

                task_metrics = TaskMetrics(
                    task_id=task.id,
                    description=task.description,
                    priority=task.priority.value,
                    status="completed",
                    duration_seconds=processing_time,
                    files_modified=len(files_modified),
                    commands_executed=len(commands_executed),
                    git_info=git_info,
                )
                self.report_generator.append_task_completion(task_metrics, project_id=task.project_id)
            except Exception as e:
                logger.error(f"Failed to append task to report: {e}")

            # Record API usage metrics
            self.scheduler.record_task_usage(
                task_id=task.id,
                total_cost_usd=usage_metrics.get("total_cost_usd"),
                duration_ms=usage_metrics.get("duration_ms"),
                duration_api_ms=usage_metrics.get("duration_api_ms"),
                num_turns=usage_metrics.get("num_turns"),
                project_id=task.project_id,
            )

            # Log performance metrics
            self.monitor.record_task_completion(processing_time, success=True)
            self.perf_logger.log_task_execution(
                task_id=task.id,
                description=task.description,
                priority=task.priority.value,
                duration_seconds=processing_time,
                success=True,
                files_modified=len(files_modified),
                commands_executed=len(commands_executed),
            )

            # Notify user via Slack if assigned
            if task.assigned_to:
                if task.priority == TaskPriority.SERIOUS:
                    priority_icon = "🔴"
                elif task.priority == TaskPriority.RANDOM:
                    priority_icon = "🟡"
                else:
                    priority_icon = "🟢"
                files_info = f"\n📝 Files modified: {len(files_modified)}" if files_modified else ""
                commands_info = f"\n⚙️ Commands: {len(commands_executed)}" if commands_executed else ""
                git_info = ""

                if git_commit_sha:
                    git_info = f"\n✅ Committed: {git_commit_sha[:8]}"

                if git_pr_url:
                    git_info += f"\n🔗 PR: {git_pr_url}"

                # Limit output to 3500 chars for Slack (safe under 4000 limit)
                output_limit = 3500
                truncated_output = result_output[:output_limit]
                if len(result_output) > output_limit:
                    truncated_output += "\n\n_[Output truncated - see result file for full content]_"

                message = (
                    f"{priority_icon} Task #{task.id} completed in {processing_time}s{files_info}{commands_info}{git_info}\n"
                    f"```{truncated_output}```"
                )
                self.bot.send_message(task.assigned_to, message)

            if self.live_status_tracker:
                self.live_status_tracker.clear(task.id)

            total_cost = usage_metrics.get("total_cost_usd") or usage_metrics.get("worker_cost_usd")
            cost_fragment = f", cost=${total_cost:.4f}" if total_cost is not None else ""
            task_summary = (
                f"Task {task.id} complete: status=success, exit_code={exit_code}, "
                f"duration={processing_time}s, files={len(files_modified)}, "
                f"commands={len(commands_executed)}{cost_fragment}"
            )

        except Exception as e:
            # Handle PauseException specially (don't mark as failed)
            from sleepless_agent.exceptions import PauseException

            if isinstance(e, PauseException):
                task_summary = (
                    f"Task {task.id} complete: execution paused until "
                    f"{e.reset_time.strftime('%Y-%m-%d %H:%M:%S')} due to usage limits."
                )
                logger.warning(
                    f"Pro plan usage limit reached during task {task.id}: "
                    f"{e.current_usage}/{e.usage_limit} ({e.percent_used:.1f}%)"
                )
                logger.info(f"Task {task.id} completed - pausing execution")
                logger.info(f"Usage will reset at {e.reset_time.strftime('%Y-%m-%d %H:%M:%S')}")

                # Mark task as completed (it finished successfully, just pausing now)
                try:
                    # Save minimal result
                    result = self.results.save_result(
                        task_id=task.id,
                        output=result_output if 'result_output' in locals() else "[Task completed before pause]",
                        files_modified=files_modified if 'files_modified' in locals() else [],
                        commands_executed=commands_executed if 'commands_executed' in locals() else [],
                        processing_time_seconds=int(time.time() - start_time) if 'start_time' in locals() else 0,
                        git_commit_sha=None,
                        git_pr_url=None,
                        git_branch=None,
                        workspace_path=str(task_workspace) if 'task_workspace' in locals() else "",
                    )
                    self.task_queue.mark_completed(task.id, result_id=result.id)
                except Exception as save_error:
                    logger.warning(f"Failed to save result before pause: {save_error}")

                # Calculate sleep time
                now = datetime.utcnow()
                sleep_seconds = max(0, (e.reset_time - now).total_seconds())

                logger.critical(
                    f"⏸️  Pausing execution for {sleep_seconds / 60:.1f} minutes "
                    f"(until {e.reset_time.strftime('%H:%M:%S')})"
                )

                # Send Slack notification
                if task.assigned_to:
                    self.bot.send_message(
                        task.assigned_to,
                        f"⏸️  Pro plan usage limit reached ({e.percent_used:.0f}%)\n"
                        f"Task #{task.id} completed successfully\n"
                        f"Pausing execution until {e.reset_time.strftime('%H:%M:%S')}\n"
                        f"Will resume automatically in ~{sleep_seconds / 60:.0f} minutes",
                    )

                if self.live_status_tracker:
                    self.live_status_tracker.clear(task.id)

                # Sleep until reset
                if sleep_seconds > 0:
                    logger.info(f"Sleeping until {e.reset_time.strftime('%H:%M:%S')}...")
                    await asyncio.sleep(sleep_seconds)

                logger.info("⏸️  Usage limit reset - resuming task processing")

                # Send resume notification
                if task.assigned_to:
                    self.bot.send_message(task.assigned_to, "▶️  Pro plan usage limit reset - resuming tasks")

                return

            # General exception handling
            logger.error(f"Failed to execute task {task.id}: {e}")
            self.task_queue.mark_failed(task.id, str(e))

            # Record failure to daily report
            try:
                task_metrics = TaskMetrics(
                    task_id=task.id,
                    description=task.description,
                    priority=task.priority.value,
                    status="failed",
                    duration_seconds=int(time.time() - start_time) if 'start_time' in locals() else 0,
                    files_modified=0,
                    commands_executed=0,
                    error_message=str(e),
                )
                self.report_generator.append_task_completion(task_metrics, project_id=task.project_id if 'task' in locals() else None)
            except Exception as report_error:
                logger.error(f"Failed to append failed task to report: {report_error}")

            # Log failure metrics
            processing_time = int(time.time() - start_time) if 'start_time' in locals() else 0
            self.monitor.record_task_completion(processing_time, success=False)
            self.perf_logger.log_task_execution(
                task_id=task.id,
                description=task.description,
                priority=task.priority.value if 'task' in locals() else "unknown",
                duration_seconds=processing_time,
                success=False,
            )

            # Notify user
            if task.assigned_to:
                self.bot.send_message(task.assigned_to, f"❌ Task #{task.id} failed: {str(e)}")

            if self.live_status_tracker:
                self.live_status_tracker.clear(task.id)

            task_summary = (
                f"Task {task.id} complete: status=failed, duration={processing_time}s, error={str(e)}"
            )
        finally:
            if task_summary:
                logger.info(task_summary)
            logger.info(separator)

    def _relative_to_workspace(self, workspace: Path, target: Path) -> Optional[str]:
        """Compute a POSIX relative path from workspace to target for git staging."""
        try:
            rel_path = os.path.relpath(target, workspace)
        except Exception as exc:
            logger.debug(f"Failed to compute relative path from {workspace} to {target}: {exc}")
            return None

        if not rel_path or rel_path == ".":
            return None

        return Path(rel_path).as_posix()

    def _collect_commit_targets(self, workspace_path: Path, base_files: Set[str]) -> List[str]:
        """Build the list of paths to stage for git commits."""
        commit_paths: Set[str] = set()

        for entry in base_files:
            if entry:
                commit_paths.add(Path(entry).as_posix())

        try:
            for file_path in self.claude.list_workspace_files(workspace_path):
                commit_paths.add(Path(file_path).as_posix())
        except Exception as exc:
            logger.debug(f"Unable to enumerate workspace files in {workspace_path}: {exc}")

        tasks_root = workspace_path.parent
        if tasks_root.exists():
            rel_tasks = self._relative_to_workspace(workspace_path, tasks_root)
            if rel_tasks:
                commit_paths.add(rel_tasks)

        workspace_root = tasks_root.parent if tasks_root else workspace_path
        data_dir = workspace_root / "data"
        if data_dir.exists():
            rel_data = self._relative_to_workspace(workspace_path, data_dir)
            if rel_data:
                commit_paths.add(rel_data)

        return sorted(path for path in commit_paths if path and path != ".")

    def _check_and_summarize_daily_reports(self):
        """Check if it's end of day and summarize reports"""
        now = datetime.utcnow()
        # Run at 23:59 UTC (11:59 PM)
        end_of_day = now.replace(hour=23, minute=59, second=0, microsecond=0)

        # If it's the first check after the cutoff time, summarize yesterday's report
        if self.last_daily_summarization is None or self.last_daily_summarization.date() != now.date():
            # Check if we're close to end of day (within last hour)
            if now >= end_of_day:
                yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
                try:
                    self.report_generator.summarize_daily_report(yesterday)
                    logger.info(f"Summarized daily report for {yesterday}")

                    # Also summarize all project reports
                    for project_id in self.report_generator.list_project_reports():
                        self.report_generator.summarize_project_report(project_id)

                    self.report_generator.update_recent_reports()
                    self.last_daily_summarization = now
                except Exception as e:
                    logger.error(f"Failed to summarize daily reports: {e}")


def main():
    """Entry point"""
    agent = SleepleassAgent()
    asyncio.run(agent.run())


if __name__ == "__main__":
    main()
