"""Main agent daemon - runs continuously"""

import asyncio
import logging
import signal
import sys
import time
from pathlib import Path

from sleepless_agent.interfaces.bot import SlackBot
from sleepless_agent.execution.claude_code_executor import ClaudeCodeExecutor
from sleepless_agent.config import get_config
from sleepless_agent.storage.git_manager import GitManager
from sleepless_agent.core.models import TaskPriority, TaskStatus, init_db
from sleepless_agent.monitoring.monitor import HealthMonitor, PerformanceLogger
from sleepless_agent.storage.results import ResultManager
from sleepless_agent.core.scheduler import SmartScheduler
from sleepless_agent.core.task_queue import TaskQueue

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class SleepleassAgent:
    """Main sleepless agent daemon"""

    def __init__(self):
        """Initialize agent"""
        self.config = get_config()
        self.running = False

        # Initialize components
        self._init_directories()
        init_db(str(self.config.agent.db_path))
        self.task_queue = TaskQueue(str(self.config.agent.db_path))
        self.scheduler = SmartScheduler(
            task_queue=self.task_queue,
            max_parallel_tasks=self.config.agent.max_parallel_tasks,
        )
        self.claude = ClaudeCodeExecutor(
            workspace_root=str(self.config.agent.workspace_root),
            default_timeout=self.config.claude_code.default_timeout,
        )
        self.results = ResultManager(
            str(self.config.agent.db_path),
            str(self.config.agent.results_path),
        )
        self.git = GitManager(workspace_root=str(self.config.agent.workspace_root))
        self.git.init_repo()
        self.git.create_random_ideas_branch()

        self.monitor = HealthMonitor(
            db_path=str(self.config.agent.db_path),
            results_path=str(self.config.agent.results_path),
        )
        self.perf_logger = PerformanceLogger(log_dir="./logs")

        self.bot = SlackBot(
            bot_token=self.config.slack.bot_token,
            app_token=self.config.slack.app_token,
            task_queue=self.task_queue,
            scheduler=self.scheduler,
            monitor=self.monitor,
        )

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _init_directories(self):
        """Initialize required directories"""
        self.config.agent.workspace_root.mkdir(parents=True, exist_ok=True)
        self.config.agent.shared_workspace.mkdir(parents=True, exist_ok=True)
        self.config.agent.results_path.mkdir(parents=True, exist_ok=True)
        Path("./logs").mkdir(parents=True, exist_ok=True)

    def _signal_handler(self, sig, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {sig}, shutting down...")
        self.running = False
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

                # Log health report every 60 seconds
                health_check_counter += 1
                if health_check_counter >= 12:  # 12 * 5 seconds = 60 seconds
                    self.monitor.log_health_report()
                    health_check_counter = 0

                await asyncio.sleep(5)  # Check tasks every 5 seconds

        except KeyboardInterrupt:
            logger.info("Agent interrupted by user")
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}")
        finally:
            self.monitor.log_health_report()
            self.bot.stop()
            logger.info("Sleepless Agent stopped")

    async def _process_tasks(self):
        """Process pending tasks using smart scheduler"""
        try:
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
        try:
            # Mark as in progress
            self.task_queue.mark_in_progress(task.id)

            logger.info(f"Executing task {task.id}: {task.description[:50]}...")

            # Execute with Claude Code SDK (async)
            start_time = time.time()
            result_output, files_modified, commands_executed, exit_code = await self.claude.execute_task(
                task_id=task.id,
                description=task.description,
                task_type="general",
                priority=task.priority.value,
                timeout=self.config.agent.task_timeout_seconds,
            )
            processing_time = int(time.time() - start_time)

            # Check if execution was successful
            if exit_code != 0:
                logger.warning(f"Task {task.id} completed with non-zero exit code: {exit_code}")
                # Note: We don't fail the task on non-zero exit, as Claude Code may still produce useful output

            # Handle git operations based on priority
            git_commit_sha = None
            git_pr_url = None
            git_branch = None

            # Get task workspace
            task_workspace = self.claude.get_workspace_path(task.id)

            if task.priority == TaskPriority.RANDOM:
                # Auto-commit random thoughts from workspace to main repo
                git_commit_sha = self.git.commit_random_thought(
                    task_id=task.id,
                    task_workspace=task_workspace,
                    description=task.description,
                    result_content=result_output,
                )

                # Clean up workspace if configured
                if self.config.claude_code.cleanup_random_workspaces:
                    try:
                        self.claude.cleanup_workspace(task.id, force=True)
                        logger.info(f"Cleaned up workspace for task {task.id}")
                    except Exception as e:
                        logger.warning(f"Failed to cleanup workspace for task {task.id}: {e}")

            elif task.priority == TaskPriority.SERIOUS and files_modified:
                # For serious tasks, workspace already has git repo
                # Validate and commit within workspace
                is_valid, validation_msg = self.git.validate_changes(
                    task_workspace, files_modified
                )

                if is_valid:
                    git_branch = f"task-{task.id}"
                    git_commit_sha = self.git.commit_in_workspace(
                        workspace=task_workspace,
                        files=files_modified,
                        message=f"Implement task: {task.description[:60]}",
                    )

                    # Create PR from workspace
                    if git_commit_sha:
                        git_pr_url = self.git.create_pr_from_workspace(
                            task_workspace=task_workspace,
                            task_id=task.id,
                            task_description=task.description,
                            branch=git_branch,
                        )
                else:
                    logger.warning(f"Validation failed for task {task.id}: {validation_msg}")

            # Save result
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

            # Mark as completed
            self.task_queue.mark_completed(task.id, result_id=result.id)

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
                priority_icon = "🔴" if task.priority.value == "serious" else "🟡"
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

            logger.info(f"Task {task.id} completed successfully")

        except Exception as e:
            logger.error(f"Failed to execute task {task.id}: {e}")
            self.task_queue.mark_failed(task.id, str(e))

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


def main():
    """Entry point"""
    agent = SleepleassAgent()
    asyncio.run(agent.run())


if __name__ == "__main__":
    main()
