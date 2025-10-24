"""Slack bot interface for task management"""

import json
from datetime import datetime
from typing import Optional

from loguru import logger
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse

from sleepless_agent.core.display import format_age_seconds, format_duration, relative_time, shorten
from sleepless_agent.core.models import TaskPriority, TaskStatus
from sleepless_agent.core.task_queue import TaskQueue
from sleepless_agent.core.task_utils import prepare_task_creation
from sleepless_agent.core.live_status import LiveStatusTracker
from sleepless_agent.monitoring.report_generator import ReportGenerator


class SlackBot:
    """Slack bot for task management"""

    def __init__(
        self,
        bot_token: str,
        app_token: str,
        task_queue: TaskQueue,
        scheduler=None,
        monitor=None,
        report_generator=None,
        live_status_tracker: Optional[LiveStatusTracker] = None,
    ):
        """Initialize Slack bot"""
        self.bot_token = bot_token
        self.app_token = app_token
        self.task_queue = task_queue
        self.scheduler = scheduler
        self.monitor = monitor
        self.report_generator = report_generator
        self.live_status_tracker = live_status_tracker
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
        elif command == "/check":
            self.handle_check_command(response_url)
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

        (
            cleaned_description,
            project_name,
            project_id,
            note,
        ) = prepare_task_creation(args)

        if not cleaned_description.strip():
            self.send_response(response_url, "Please provide a task description")
            return

        self._create_task(
            description=cleaned_description.strip(),
            priority=TaskPriority.SERIOUS,
            response_url=response_url,
            user_id=user_id,
            note=note,
            project_name=project_name,
            project_id=project_id,
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

        cleaned_description, project_name, project_id, helper_note = prepare_task_creation(description)

        self._create_task(
            description=cleaned_description,
            priority=TaskPriority.RANDOM,
            response_url=response_url,
            user_id=user_id,
            note=helper_note,
            project_name=project_name,
            project_id=project_id,
        )

    def _create_task(
        self,
        description: str,
        priority: TaskPriority,
        response_url: str,
        user_id: str,
        note: Optional[str] = None,
        project_name: Optional[str] = None,
        project_id: Optional[str] = None,
    ):
        """Create a task and send a Slack response"""
        try:
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

    def handle_check_command(self, response_url: str):
        """Handle /check command - comprehensive system status"""
        try:
            blocks = self._build_check_blocks()
            fallback_message = self._build_check_message()
            self.send_response(response_url, message=fallback_message, blocks=blocks)
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

    def send_response(self, response_url: str, message: str = None, blocks: list = None):
        """Send response to Slack

        Args:
            response_url: Slack response URL
            message: Plain text fallback message
            blocks: Block Kit blocks for rich formatting
        """
        try:
            import requests
            payload = {}

            # If blocks provided, use them; otherwise use plain text
            if blocks:
                payload["blocks"] = blocks
            if message:
                payload["text"] = message

            # Ensure at least text or blocks are provided
            if not payload:
                payload["text"] = "No message"

            requests.post(
                response_url,
                json=payload,
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

    def _block_header(self, text: str) -> dict:
        """Create a header block"""
        return {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": text,
                "emoji": True
            }
        }

    def _block_divider(self) -> dict:
        """Create a divider block"""
        return {"type": "divider"}

    def _block_section(self, text: str, markdown: bool = False) -> dict:
        """Create a section block with text"""
        return {
            "type": "section",
            "text": {
                "type": "mrkdwn" if markdown else "plain_text",
                "text": text,
                "emoji": True
            }
        }

    def _block_section_fields(self, fields: list[dict]) -> dict:
        """Create a section block with fields

        Args:
            fields: List of dicts with 'label' and 'value' keys
        """
        field_blocks = []
        for field in fields:
            field_blocks.append({
                "type": "mrkdwn",
                "text": f"*{field['label']}*\n{field['value']}"
            })
        return {
            "type": "section",
            "fields": field_blocks
        }

    def _block_context(self, text: str) -> dict:
        """Create a context block for metadata"""
        return {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": text
                }
            ]
        }

    def _build_check_blocks(self) -> list[dict]:
        """Build Block Kit blocks for status check response"""
        escape = self._escape_slack
        blocks = []

        health = self.monitor.check_health() if self.monitor else {}
        status = str(health.get("status", "unknown"))
        status_emoji = {
            "healthy": "✅",
            "degraded": "⚠️",
            "unhealthy": "❌",
        }.get(status.lower(), "❔")

        system = health.get("system", {})

        def fmt_percent(value):
            if isinstance(value, (int, float)):
                return f"{float(value):.1f}"
            if value in (None, ""):
                return "N/A"
            return str(value)

        uptime = escape(health.get("uptime_human", "< 1m"))
        cpu_text = fmt_percent(system.get("cpu_percent"))
        mem_text = fmt_percent(system.get("memory_percent"))

        # Header with status
        blocks.append(self._block_header(f"{status_emoji} Sleepless Agent Status"))

        # System info
        blocks.append(self._block_section(
            f"Uptime: `{uptime}` · CPU: `{cpu_text}%` · Memory: `{mem_text}%`",
            markdown=True
        ))

        blocks.append(self._block_divider())

        # Queue section
        blocks.append(self._block_header("Queue"))
        queue_status = self.task_queue.get_queue_status()
        queue_fields = [
            {"label": "Pending", "value": str(queue_status['pending'])},
            {"label": "In Progress", "value": str(queue_status['in_progress'])},
            {"label": "Completed", "value": str(queue_status['completed'])},
            {"label": "Failed", "value": str(queue_status['failed'])},
        ]
        blocks.append(self._block_section_fields(queue_fields))

        # Lifetime stats if available
        if self.monitor:
            stats = self.monitor.get_stats()
            success_rate = stats.get("success_rate")
            success_text = f"{success_rate:.1f}%" if success_rate is not None else "—"
            lifetime_info = f"*Lifetime:* Completed `{stats['tasks_completed']}`, Failed `{stats['tasks_failed']}`, Success `{success_text}`"
            if stats.get("avg_processing_time") is not None:
                lifetime_info += f" · Avg Duration `{format_duration(stats.get('avg_processing_time'))}`"
            blocks.append(self._block_section(lifetime_info, markdown=True))

        blocks.append(self._block_divider())

        # Active tasks section
        blocks.append(self._block_header("Active Tasks"))
        running_tasks = self.task_queue.get_in_progress_tasks()
        if running_tasks:
            for task in running_tasks[:3]:
                project = task.project_name or task.project_id or "—"
                project_text = escape(project)
                owner = f"<@{task.assigned_to}>" if task.assigned_to else "—"
                elapsed_seconds = (
                    (datetime.utcnow() - task.started_at).total_seconds()
                    if task.started_at
                    else None
                )
                elapsed_text = format_duration(elapsed_seconds)
                description = escape(shorten(task.description, 80))
                task_text = f"*#{task.id}* `{project_text}` — {description}\n_Owner: {owner} · Elapsed: {elapsed_text}_"
                blocks.append(self._block_section(task_text, markdown=True))
        else:
            blocks.append(self._block_section("No active tasks", markdown=True))

        blocks.append(self._block_divider())

        # Pending tasks section
        blocks.append(self._block_header("Next Up"))
        pending_tasks = self.task_queue.get_pending_tasks(limit=3)
        if pending_tasks:
            for task in pending_tasks:
                project = task.project_name or task.project_id
                context_parts = []
                if project:
                    context_parts.append(f"`{escape(project)}`")
                context_parts.append(f"queued {relative_time(task.created_at)}")
                context = " · ".join(context_parts)
                description = escape(shorten(task.description, 80))
                priority = task.priority.value.capitalize()
                task_text = f"*#{task.id} {priority}* — {description}\n_{context}_"
                blocks.append(self._block_section(task_text, markdown=True))
        else:
            blocks.append(self._block_section("Queue is clear", markdown=True))

        # Projects section
        projects = self.task_queue.get_projects()
        if projects:
            blocks.append(self._block_divider())
            blocks.append(self._block_header("Projects"))
            projects_sorted = sorted(projects, key=lambda p: p["total_tasks"], reverse=True)
            display_limit = 4
            for proj in projects_sorted[:display_limit]:
                name = escape(proj["project_name"] or proj["project_id"] or "—")
                proj_text = f"*{name}*\nPending: `{proj['pending']}` · Running: `{proj['in_progress']}` · Completed: `{proj['completed']}`"
                blocks.append(self._block_section(proj_text, markdown=True))
            if len(projects_sorted) > display_limit:
                blocks.append(self._block_context(f"… and {len(projects_sorted) - display_limit} more projects"))

        blocks.append(self._block_divider())

        # Storage section
        blocks.append(self._block_header("Storage"))
        db = health.get("database", {})
        storage = health.get("storage", {})
        storage_fields = []
        if db:
            if db.get("accessible"):
                storage_fields.append({
                    "label": "Database",
                    "value": f"{db.get('size_mb', 'N/A')} MB (updated {format_age_seconds(db.get('modified_ago_seconds'))})"
                })
            else:
                storage_fields.append({"label": "Database", "value": "unavailable"})
        if storage:
            if storage.get("accessible"):
                storage_fields.append({
                    "label": "Results",
                    "value": f"{storage.get('count', 0)} files · {storage.get('total_size_mb', 0)} MB"
                })
            else:
                storage_fields.append({"label": "Results", "value": "unavailable"})
        if storage_fields:
            blocks.append(self._block_section_fields(storage_fields))

        # Usage section
        budget_info = None
        if self.scheduler:
            try:
                budget_info = self.scheduler.get_credit_status()
            except Exception as exc:
                logger.debug(f"Failed to fetch credit status: {exc}")

        if budget_info:
            blocks.append(self._block_divider())
            blocks.append(self._block_header("Usage"))
            budget = budget_info.get("budget", {})
            window = budget_info.get("current_window", {})

            period = "Night" if budget.get("is_nighttime") else "Day"
            remaining = budget.get("remaining_budget_usd")
            quota = budget.get("current_quota_usd")
            remaining_val = None
            quota_val = None
            try:
                if remaining is not None:
                    remaining_val = float(remaining)
                if quota is not None:
                    quota_val = float(quota)
            except (TypeError, ValueError):
                remaining_val = quota_val = None

            usage_fields = []
            if remaining_val is not None and quota_val is not None:
                usage_fields.append({
                    "label": f"{period} Period",
                    "value": f"${remaining_val:.2f} / ${quota_val:.2f}"
                })

            if window:
                executed = window.get("tasks_executed", 0) or 0
                remaining_minutes = window.get("time_remaining_minutes") or 0
                usage_fields.append({
                    "label": "Window",
                    "value": f"{executed} tasks · {format_duration(remaining_minutes * 60)} left"
                })

            if usage_fields:
                blocks.append(self._block_section_fields(usage_fields))

        blocks.append(self._block_divider())

        # Recent activity section
        blocks.append(self._block_header("Recent Activity"))
        recent_tasks = self.task_queue.get_recent_tasks(limit=5)
        if recent_tasks:
            status_icons = {
                TaskStatus.COMPLETED: "✅",
                TaskStatus.IN_PROGRESS: "🔄",
                TaskStatus.PENDING: "🕒",
                TaskStatus.FAILED: "❌",
                TaskStatus.CANCELLED: "🗑️",
            }
            for task in recent_tasks:
                icon = status_icons.get(task.status, "•")
                description = escape(shorten(task.description, 70))
                status_label = task.status.value.replace('_', ' ')
                activity_text = f"{icon} *#{task.id}* {description}\n_{status_label} · {relative_time(task.created_at)}_"
                blocks.append(self._block_section(activity_text, markdown=True))
        else:
            blocks.append(self._block_section("No recent activity", markdown=True))

        return blocks

    def _build_check_message(self) -> str:
        escape = self._escape_slack

        health = self.monitor.check_health() if self.monitor else {}
        status = str(health.get("status", "unknown"))
        status_emoji = {
            "healthy": "✅",
            "degraded": "⚠️",
            "unhealthy": "❌",
        }.get(status.lower(), "❔")

        system = health.get("system", {})

        def fmt_percent(value):
            if isinstance(value, (int, float)):
                return f"{float(value):.1f}"
            if value in (None, ""):
                return "N/A"
            return str(value)

        uptime = escape(health.get("uptime_human", "< 1m"))
        cpu_text = fmt_percent(system.get("cpu_percent"))
        mem_text = fmt_percent(system.get("memory_percent"))

        lines: list[str] = []
        lines.append("*Sleepless Agent Status*")
        lines.append(
            f"{status_emoji} *{escape(status.upper())}* · "
            f"Uptime `{uptime}` · CPU `{cpu_text}%` · Memory `{mem_text}%`"
        )

        queue_status = self.task_queue.get_queue_status()
        lines.append("")
        lines.append("*Queue*")
        lines.append(
            f"• Pending *{queue_status['pending']}* | "
            f"In progress *{queue_status['in_progress']}* | "
            f"Completed *{queue_status['completed']}* | "
            f"Failed *{queue_status['failed']}*"
        )

        if self.monitor:
            stats = self.monitor.get_stats()
            success_rate = stats.get("success_rate")
            success_text = f"{success_rate:.1f}%" if success_rate is not None else "—"
            lines.append(
                f"• Lifetime: Completed *{stats['tasks_completed']}*, "
                f"Failed *{stats['tasks_failed']}*, Success {success_text}"
            )
            avg_time = stats.get("avg_processing_time")
            if avg_time is not None:
                lines.append(f"• Avg Duration: {format_duration(avg_time)}")

        live_entries = []
        if self.live_status_tracker:
            try:
                live_entries = self.live_status_tracker.entries()
            except Exception as exc:  # pragma: no cover - diagnostics
                logger.debug(f"Live status unavailable: {exc}")
                live_entries = []

        lines.append("")
        lines.append("*Live Sessions*")
        if live_entries:
            max_items = 3
            for entry in live_entries[:max_items]:
                try:
                    updated_dt = datetime.fromisoformat(entry.updated_at)
                except Exception:
                    updated_dt = None
                age_text = relative_time(updated_dt) if updated_dt else "just now"
                phase_text = escape(entry.phase.replace("_", " ").title())
                status_text = escape(entry.status.replace("_", " ").title())
                query_preview = escape(shorten(entry.prompt_preview or "—", 60))
                answer_preview = escape(shorten(entry.answer_preview or "—", 40))
                lines.append(
                    f"• #{entry.task_id} {phase_text} ({status_text}) — \"{query_preview}\" -> \"{answer_preview}\" [{age_text}]"
                )
            remaining = len(live_entries) - max_items
            if remaining > 0:
                lines.append(f"• ... {remaining} more session(s)")
        else:
            lines.append("• None")

        running_tasks = self.task_queue.get_in_progress_tasks()
        lines.append("")
        lines.append("*Active Tasks*")
        if running_tasks:
            for task in running_tasks[:3]:
                project = task.project_name or task.project_id or "—"
                project_text = escape(project)
                owner = f"<@{task.assigned_to}>" if task.assigned_to else "—"
                elapsed_seconds = (
                    (datetime.utcnow() - task.started_at).total_seconds()
                    if task.started_at
                    else None
                )
                elapsed_text = format_duration(elapsed_seconds)
                description = escape(shorten(task.description, 80))
                lines.append(
                    f"• #{task.id} `{project_text}` — {description} "
                    f"(owner {owner}, elapsed {elapsed_text})"
                )
        else:
            lines.append("• None")

        pending_tasks = self.task_queue.get_pending_tasks(limit=3)
        lines.append("")
        lines.append("*Next Up*")
        if pending_tasks:
            for task in pending_tasks:
                project = task.project_name or task.project_id
                context_parts = []
                if project:
                    context_parts.append(f"`{escape(project)}`")
                context_parts.append(f"queued {relative_time(task.created_at)}")
                context = " · ".join(context_parts)
                description = escape(shorten(task.description, 80))
                priority = task.priority.value.capitalize()
                lines.append(f"• #{task.id} {priority} — {description} ({context})")
        else:
            lines.append("• Queue is clear")

        projects = self.task_queue.get_projects()
        if projects:
            lines.append("")
            lines.append("*Projects*")
            projects_sorted = sorted(projects, key=lambda p: p["total_tasks"], reverse=True)
            display_limit = 4
            for proj in projects_sorted[:display_limit]:
                name = escape(proj["project_name"] or proj["project_id"] or "—")
                lines.append(
                    f"• {name} — pending {proj['pending']}, "
                    f"running {proj['in_progress']}, completed {proj['completed']}"
                )
            if len(projects_sorted) > display_limit:
                lines.append(f"• … and {len(projects_sorted) - display_limit} more")

        db = health.get("database", {})
        storage = health.get("storage", {})
        lines.append("")
        lines.append("*Storage*")
        if db:
            if db.get("accessible"):
                lines.append(
                    f"• DB: {db.get('size_mb', 'N/A')} MB "
                    f"(updated {format_age_seconds(db.get('modified_ago_seconds'))})"
                )
            else:
                lines.append("• DB: unavailable")
        if storage:
            if storage.get("accessible"):
                lines.append(
                    f"• Results: {storage.get('count', 0)} files · "
                    f"{storage.get('total_size_mb', 0)} MB"
                )
            else:
                lines.append("• Results: unavailable")

        budget_info = None
        if self.scheduler:
            try:
                budget_info = self.scheduler.get_credit_status()
            except Exception as exc:
                logger.debug(f"Failed to fetch credit status: {exc}")

        if budget_info:
            budget = budget_info.get("budget", {})
            window = budget_info.get("current_window", {})
            lines.append("")
            lines.append("*Usage*")

            period = "Night" if budget.get("is_nighttime") else "Day"
            remaining = budget.get("remaining_budget_usd")
            quota = budget.get("current_quota_usd")
            remaining_val = None
            quota_val = None
            try:
                if remaining is not None:
                    remaining_val = float(remaining)
                if quota is not None:
                    quota_val = float(quota)
            except (TypeError, ValueError):
                remaining_val = quota_val = None

            if remaining_val is not None and quota_val is not None:
                lines.append(
                    f"• {period} period · Remaining ${remaining_val:.2f} / ${quota_val:.2f}"
                )

            if window:
                executed = window.get("tasks_executed", 0) or 0
                remaining_minutes = window.get("time_remaining_minutes") or 0
                lines.append(
                    f"• Window: {executed} tasks · "
                    f"{format_duration(remaining_minutes * 60)} left"
                )

        recent_tasks = self.task_queue.get_recent_tasks(limit=5)
        if recent_tasks:
            lines.append("")
            lines.append("*Recent Activity*")
            status_icons = {
                TaskStatus.COMPLETED: "✅",
                TaskStatus.IN_PROGRESS: "🔄",
                TaskStatus.PENDING: "🕒",
                TaskStatus.FAILED: "❌",
                TaskStatus.CANCELLED: "🗑️",
            }
            for task in recent_tasks:
                icon = status_icons.get(task.status, "•")
                description = escape(shorten(task.description, 70))
                lines.append(
                    f"{icon} #{task.id} {description} — "
                    f"{task.status.value.replace('_', ' ')} ({relative_time(task.created_at)})"
                )

        return "\n".join(lines)

    def _escape_slack(self, text: Optional[str]) -> str:
        if text is None:
            return ""
        text = str(text)
        replacements = {"&": "&amp;", "<": "&lt;", ">": "&gt;"}
        for char, replacement in replacements.items():
            text = text.replace(char, replacement)
        for char in ("*", "_", "`", "~"):
            text = text.replace(char, f"\\{char}")
        return text
