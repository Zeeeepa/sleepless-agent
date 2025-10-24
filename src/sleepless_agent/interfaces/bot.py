"""Slack bot interface for task management"""

import json
import re
from typing import Optional

from loguru import logger
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse

from sleepless_agent.core.models import TaskPriority
from sleepless_agent.core.task_queue import TaskQueue
from sleepless_agent.monitoring.report_generator import ReportGenerator


def _slugify_project(identifier: str) -> str:
    """Convert project name/id to slugified project_id (auto-detect)."""
    return re.sub(r'[^a-z0-9-]', '-', identifier.lower())


class SlackBot:
    """Slack bot for task management"""

    def __init__(self, bot_token: str, app_token: str, task_queue: TaskQueue, scheduler=None, monitor=None, report_generator=None):
        """Initialize Slack bot"""
        self.bot_token = bot_token
        self.app_token = app_token
        self.task_queue = task_queue
        self.scheduler = scheduler
        self.monitor = monitor
        self.report_generator = report_generator
        self.client = WebClient(token=bot_token)
        self.socket_mode_client = SocketModeClient(app_token=app_token, web_client=self.client)

    def start(self):
        """Start bot and listen for events"""
        self.socket_mode_client.socket_mode_request_listeners.append(self.handle_event)
        self.socket_mode_client.connect()
        logger.info("Slack bot started and listening for events")

    def stop(self):
        """Stop bot"""
        self.socket_mode_client.close()
        logger.info("Slack bot stopped")

    def handle_event(self, client: SocketModeClient, req: SocketModeRequest):
        """Handle incoming Slack events"""
        try:
            if req.type == "events_api":
                self.handle_events_api(req)
                client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))
            elif req.type == "slash_commands":
                self.handle_slash_command(req)
                client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))
        except Exception as e:
            logger.error(f"Error handling event: {e}")
            client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))

    def handle_events_api(self, req: SocketModeRequest):
        """Handle events API"""
        if req.payload["event"]["type"] == "message":
            self.handle_message(req.payload["event"])

    def handle_message(self, event: dict):
        """Handle incoming messages"""
        # Ignore bot messages
        if event.get("bot_id"):
            return

        channel = event.get("channel")
        user = event.get("user")
        text = event.get("text", "").strip()

        logger.info(f"Message from {user}: {text}")

    def handle_slash_command(self, req: SocketModeRequest):
        """Handle slash commands"""
        command = req.payload["command"]
        text = req.payload.get("text", "").strip()
        user = req.payload["user_id"]
        channel = req.payload["channel_id"]
        response_url = req.payload.get("response_url")

        logger.info(f"Slash command: {command} {text} from {user}")

        if command == "/task":
            self.handle_task_command(text, user, channel, response_url)
        elif command == "/think":
            self.handle_think_command(text, user, channel, response_url)
        elif command == "/status":
            self.handle_status_command(response_url)
        elif command == "/cancel":
            self.handle_cancel_command(text, response_url)
        elif command == "/report":
            self.handle_report_command(text, response_url)
        elif command == "/trash":
            self.handle_trash_command(text, response_url)
        else:
            self.send_response(response_url, f"Unknown command: {command}")

    def handle_task_command(
        self,
        args: str,
        user_id: str,
        channel_id: str,
        response_url: str,
    ):
        """Handle /task command for serious work

        Usage: /task <description> [--project=<project_name>]
        """
        if not args:
            self.send_response(response_url, "Usage: /task <description> [--project=<project_name>]")
            return

        description = args.strip()
        note: Optional[str] = None
        project_name: Optional[str] = None

        # Parse --project flag
        if "--project=" in description:
            import re
            match = re.search(r'--project=(\S+)', description)
            if match:
                project_name = match.group(1)
                description = description.replace(f"--project={project_name}", "").strip()

        if "--serious" in description:
            description = description.replace("--serious", "").strip()
            note = "ℹ️ `--serious` flag no longer needed; `/task` is always serious."

        if "--random" in description:
            description = description.replace("--random", "").strip()
            note = (
                "ℹ️ Random ideas belong in `/think`. We'll treat this as a serious task."
            )

        if not description:
            self.send_response(response_url, "Please provide a task description")
            return

        self._create_task(
            description=description,
            priority=TaskPriority.SERIOUS,
            response_url=response_url,
            user_id=user_id,
            note=note,
            project_name=project_name,
        )

    def handle_think_command(
        self,
        args: str,
        user_id: str,
        channel_id: str,
        response_url: str,
    ):
        """Handle /think command for lightweight ideas"""
        if not args:
            self.send_response(response_url, "Usage: /think <description>")
            return

        description = args.strip()

        if "--serious" in description:
            description = description.replace("--serious", "").strip()
            self.send_response(
                response_url,
                "`/think` is for casual ideas. Use `/task` for serious work.",
            )
            return

        if not description:
            self.send_response(response_url, "Please provide a thought to capture")
            return

        self._create_task(
            description=description,
            priority=TaskPriority.RANDOM,
            response_url=response_url,
            user_id=user_id,
        )

    def _create_task(
        self,
        description: str,
        priority: TaskPriority,
        response_url: str,
        user_id: str,
        note: Optional[str] = None,
        project_name: Optional[str] = None,
    ):
        """Create a task and send a Slack response"""
        try:
            # Generate project_id from project_name (simple slug)
            project_id = None
            if project_name:
                import re
                project_id = re.sub(r'[^a-z0-9-]', '-', project_name.lower())

            task = self.task_queue.add_task(
                description=description,
                priority=priority,
                slack_user_id=user_id,
                project_id=project_id,
                project_name=project_name,
            )

            if priority == TaskPriority.SERIOUS:
                priority_label = "🔴 Serious task"
            elif priority == TaskPriority.RANDOM:
                priority_label = "🟡 Thought"
            else:
                priority_label = "🟢 Generated task"

            project_info = f"\n📁 Project: {project_name}" if project_name else ""
            message = f"{priority_label}\nTask #{task.id} added to queue{project_info}\n```{description}```"
            if note:
                message = f"{note}\n\n{message}"

            self.send_response(response_url, message)
            logger.info(f"Task {task.id} added by {user_id}" + (f" [Project: {project_name}]" if project_name else ""))

        except Exception as e:
            self.send_response(response_url, f"Failed to add task: {str(e)}")
            logger.error(f"Failed to add task: {e}")

    def handle_status_command(self, response_url: str):
        """Handle /status command - comprehensive system status"""
        try:
            # System health
            health = self.monitor.check_health() if self.monitor else {}
            status_emoji = {
                "healthy": "✅",
                "degraded": "⚠️",
                "unhealthy": "❌",
            }.get(health.get("status", "unknown"), "❓")

            system = health.get("system", {})

            message = (
                f"{status_emoji} System: {health.get('status', 'unknown').upper()}\n"
                f"⏱️ Uptime: {health.get('uptime_human', 'N/A')}\n"
                f"🖥️ CPU: {system.get('cpu_percent', 'N/A')}%\n"
                f"💾 Memory: {system.get('memory_percent', 'N/A')}%\n\n"
            )

            # Queue status
            queue_status = self.task_queue.get_queue_status()
            message += (
                f"📊 Queue\n"
                f"Total: {queue_status['total']}\n"
                f"Pending: {queue_status['pending']}\n"
                f"In Progress: {queue_status['in_progress']}\n"
                f"Completed: {queue_status['completed']}\n"
                f"Failed: {queue_status['failed']}"
            )

            self.send_response(response_url, message)
        except Exception as e:
            self.send_response(response_url, f"Failed to get status: {str(e)}")
            logger.error(f"Failed to get status: {e}")

    def handle_cancel_command(self, identifier_str: str, response_url: str):
        """Handle /cancel command - move task or project to trash

        Usage: /cancel <task_id> or /cancel <project_id_or_name>
        """
        try:
            if not identifier_str:
                self.send_response(response_url, "Usage: /cancel <task_id_or_project>")
                return

            # Try to parse as integer (task ID)
            try:
                task_id = int(identifier_str)
                task = self.task_queue.cancel_task(task_id)
                if task:
                    self.send_response(response_url, f"Task #{task_id} moved to trash")
                else:
                    self.send_response(response_url, f"Task #{task_id} not found or already running")
                return
            except ValueError:
                pass

            # Try to interpret as project ID
            project_id = _slugify_project(identifier_str)
            project = self.task_queue.get_project_by_id(project_id)

            if not project:
                self.send_response(response_url, f"Project not found: {identifier_str}")
                return

            # Soft delete tasks from database
            count = self.task_queue.delete_project(project_id)
            message = f"✅ Moved {count} task(s) to trash in database\n"

            # Move workspace to trash
            from datetime import datetime
            from pathlib import Path
            import shutil

            workspace_path = Path("workspace") / "projects" / project_id
            if workspace_path.exists():
                trash_dir = Path("workspace") / "trash"
                trash_dir.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                trash_path = trash_dir / f"project_{project_id}_{timestamp}"
                workspace_path.rename(trash_path)
                message += f"✅ Moved workspace to trash"
            else:
                message += f"⚠️ Workspace not found (no workspace to move)"

            self.send_response(response_url, message)

        except Exception as e:
            self.send_response(response_url, f"Failed to move to trash: {str(e)}")
            logger.error(f"Failed to cancel: {e}")

    def send_response(self, response_url: str, message: str):
        """Send response to Slack"""
        try:
            import requests
            requests.post(
                response_url,
                json={"text": message},
                timeout=5,
            )
        except Exception as e:
            logger.error(f"Failed to send response: {e}")

    def send_message(self, channel: str, message: str):
        """Send message to channel"""
        try:
            self.client.chat_postMessage(channel=channel, text=message, mrkdwn=True)
        except SlackApiError as e:
            logger.error(f"Failed to send message: {e}")

    def send_thread_message(self, channel: str, thread_ts: str, message: str):
        """Send message to thread"""
        try:
            self.client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=message,
                mrkdwn=True,
            )
        except SlackApiError as e:
            logger.error(f"Failed to send thread message: {e}")

    def handle_trash_command(self, args: str, response_url: str):
        """Handle /trash command - manage trash (list, restore, empty)

        Usage:
            /trash list       - Show trash contents
            /trash restore <project> - Restore project from trash
            /trash empty      - Permanently delete trash
        """
        from pathlib import Path
        import shutil

        subcommand = args.split()[0].lower() if args else "list"
        remaining_args = args[len(subcommand):].strip() if args else ""

        if subcommand == "list":
            try:
                trash_dir = Path("workspace") / "trash"
                if not trash_dir.exists():
                    self.send_response(response_url, "🗑️ Trash is empty")
                    return

                items = list(trash_dir.iterdir())
                if not items:
                    self.send_response(response_url, "🗑️ Trash is empty")
                    return

                message = "🗑️ Trash Contents:\n"
                for item in sorted(items):
                    if item.is_dir():
                        size_mb = sum(f.stat().st_size for f in item.rglob("*") if f.is_file()) / (1024 * 1024)
                        message += f"  📁 {item.name} ({size_mb:.1f} MB)\n"
                self.send_response(response_url, message)
            except Exception as e:
                self.send_response(response_url, f"Failed to list trash: {str(e)}")
                logger.error(f"Failed to list trash: {e}")

        elif subcommand == "restore":
            try:
                if not remaining_args:
                    self.send_response(response_url, "Usage: /trash restore <project_id_or_name>")
                    return

                trash_dir = Path("workspace") / "trash"
                if not trash_dir.exists():
                    self.send_response(response_url, "🗑️ Trash is empty")
                    return

                # Find matching item in trash
                search_term = remaining_args.lower().replace(" ", "-")
                matching_items = [item for item in trash_dir.iterdir() if search_term in item.name.lower()]

                if not matching_items:
                    self.send_response(response_url, f"Project not found in trash: {remaining_args}")
                    return

                if len(matching_items) > 1:
                    message = f"Multiple matches found for '{remaining_args}'. Be more specific:\n"
                    for item in matching_items:
                        message += f"  - {item.name}\n"
                    self.send_response(response_url, message)
                    return

                trash_item = matching_items[0]

                # Extract project_id from trash item name (e.g., "project_myapp_20231015_120000")
                parts = trash_item.name.split("_")
                if parts[0] != "project":
                    self.send_response(response_url, f"Invalid trash item format: {trash_item.name}")
                    return

                # Reconstruct project_id (everything except the last timestamp)
                project_id = "_".join(parts[1:-2])  # Remove "project" prefix and timestamp parts

                # Restore workspace
                workspace_path = Path("workspace") / "projects" / project_id
                if workspace_path.exists():
                    self.send_response(response_url, f"Workspace already exists at {workspace_path}")
                    return

                trash_item.rename(workspace_path)
                self.send_response(
                    response_url,
                    f"✅ Restored project '{project_id}' from trash\n"
                    f"⚠️ Note: Tasks remain in CANCELLED status. Update them manually if needed."
                )
            except Exception as e:
                self.send_response(response_url, f"Failed to restore from trash: {str(e)}")
                logger.error(f"Failed to restore from trash: {e}")

        elif subcommand == "empty":
            try:
                trash_dir = Path("workspace") / "trash"
                if not trash_dir.exists() or not list(trash_dir.iterdir()):
                    self.send_response(response_url, "🗑️ Trash is already empty")
                    return

                count = 0
                for item in trash_dir.iterdir():
                    if item.is_dir():
                        shutil.rmtree(item)
                        count += 1

                self.send_response(response_url, f"✅ Deleted {count} item(s) from trash")
            except Exception as e:
                self.send_response(response_url, f"Failed to empty trash: {str(e)}")
                logger.error(f"Failed to empty trash: {e}")

        else:
            self.send_response(
                response_url,
                "Usage: /trash list|restore|empty\n"
                "  `list` - Show trash contents\n"
                "  `restore <project>` - Restore project from trash\n"
                "  `empty` - Permanently delete all trash"
            )

    def handle_report_command(self, identifier: str, response_url: str):
        """Handle /report command - unified report handler (task/daily/project)

        Usage:
            /report              # Today's daily report
            /report 123          # Task #123 details
            /report 2025-10-22   # Specific date report
            /report <project>    # Project report
            /report --list       # List all available reports
        """
        try:
            if not self.report_generator:
                self.send_response(response_url, "Report generator not available")
                return

            args = identifier.strip() if identifier else ""

            # Check for --list flag
            if "--list" in args:
                daily_reports = self.report_generator.list_daily_reports()
                project_reports = self.report_generator.list_project_reports()

                message = ""
                if daily_reports:
                    message += "📅 Daily Reports:\n"
                    for report_date in daily_reports[:5]:
                        message += f"  • {report_date}\n"
                    if len(daily_reports) > 5:
                        message += f"  ... and {len(daily_reports) - 5} more\n"
                else:
                    message += "📅 No daily reports\n"

                if project_reports:
                    message += "\n📦 Project Reports:\n"
                    for project_id in project_reports:
                        message += f"  • {project_id}\n"
                else:
                    message += "📦 No project reports"

                self.send_response(response_url, message)
                return

            # Determine if it's a date or project
            if not args:
                # Default: today's report
                from datetime import datetime
                date = datetime.utcnow().strftime("%Y-%m-%d")
                report = self.report_generator.get_daily_report(date)
            else:
                # Try to parse as date
                try:
                    from datetime import datetime
                    datetime.strptime(args, "%Y-%m-%d")
                    report = self.report_generator.get_daily_report(args)
                except ValueError:
                    # Not a date, treat as project ID
                    report = self.report_generator.get_project_report(args)

            # Truncate if too long for Slack
            max_length = 3000
            if len(report) > max_length:
                report = report[:max_length] + "\n\n_[Report truncated - use CLI for full content]_"

            self.send_response(response_url, f"```{report}```")

        except Exception as e:
            self.send_response(response_url, f"Failed to get report: {str(e)}")
            logger.error(f"Failed to get report: {e}")
