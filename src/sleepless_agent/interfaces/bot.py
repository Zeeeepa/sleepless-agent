"""Slack bot interface for task management"""

import json
import logging
from typing import Optional

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_sdk.socket_mode import SocketModeClient
from slack_sdk.socket_mode.request import SocketModeRequest
from slack_sdk.socket_mode.response import SocketModeResponse

from sleepless_agent.core.models import TaskPriority
from sleepless_agent.core.task_queue import TaskQueue

logger = logging.getLogger(__name__)


class SlackBot:
    """Slack bot for task management"""

    def __init__(self, bot_token: str, app_token: str, task_queue: TaskQueue, scheduler=None, monitor=None):
        """Initialize Slack bot"""
        self.bot_token = bot_token
        self.app_token = app_token
        self.task_queue = task_queue
        self.scheduler = scheduler
        self.monitor = monitor
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
        elif command == "/results":
            self.handle_results_command(text, response_url)
        elif command == "/priority":
            self.handle_priority_command(text, response_url)
        elif command == "/cancel":
            self.handle_cancel_command(text, response_url)
        elif command == "/credits":
            self.handle_credits_command(response_url)
        elif command == "/health":
            self.handle_health_command(response_url)
        elif command == "/metrics":
            self.handle_metrics_command(response_url)
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
            else:
                priority_label = "🟡 Thought"

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
        """Handle /status command"""
        try:
            status = self.task_queue.get_queue_status()
            message = (
                f"📊 Queue Status\n"
                f"Total: {status['total']}\n"
                f"Pending: {status['pending']}\n"
                f"In Progress: {status['in_progress']}\n"
                f"Completed: {status['completed']}\n"
                f"Failed: {status['failed']}"
            )
            self.send_response(response_url, message)
        except Exception as e:
            self.send_response(response_url, f"Failed to get status: {str(e)}")
            logger.error(f"Failed to get status: {e}")

    def handle_results_command(self, task_id_str: str, response_url: str):
        """Handle /results command"""
        try:
            if not task_id_str:
                self.send_response(response_url, "Usage: /results <task_id>")
                return

            task_id = int(task_id_str)
            task = self.task_queue.get_task(task_id)

            if not task:
                self.send_response(response_url, f"Task #{task_id} not found")
                return

            message = f"Task #{task.id}\nStatus: {task.status.value}\nPriority: {task.priority.value}"
            if task.error_message:
                message += f"\nError: {task.error_message}"

            self.send_response(response_url, message)

        except ValueError:
            self.send_response(response_url, "Invalid task ID")
        except Exception as e:
            self.send_response(response_url, f"Failed to get results: {str(e)}")
            logger.error(f"Failed to get results: {e}")

    def handle_priority_command(self, args: str, response_url: str):
        """Handle /priority command"""
        try:
            parts = args.split()
            if len(parts) != 2:
                self.send_response(response_url, "Usage: /priority <task_id> random|serious")
                return

            task_id = int(parts[0])
            priority_str = parts[1].lower()

            if priority_str not in ["random", "serious"]:
                self.send_response(response_url, "Priority must be 'random' or 'serious'")
                return

            priority = TaskPriority.RANDOM if priority_str == "random" else TaskPriority.SERIOUS
            task = self.task_queue.update_priority(task_id, priority)

            if task:
                self.send_response(response_url, f"Task #{task_id} priority updated to {priority.value}")
            else:
                self.send_response(response_url, f"Task #{task_id} not found")

        except ValueError:
            self.send_response(response_url, "Invalid task ID")
        except Exception as e:
            self.send_response(response_url, f"Failed to update priority: {str(e)}")
            logger.error(f"Failed to update priority: {e}")

    def handle_cancel_command(self, task_id_str: str, response_url: str):
        """Handle /cancel command"""
        try:
            if not task_id_str:
                self.send_response(response_url, "Usage: /cancel <task_id>")
                return

            task_id = int(task_id_str)
            task = self.task_queue.cancel_task(task_id)

            if task:
                self.send_response(response_url, f"Task #{task_id} cancelled")
            else:
                self.send_response(response_url, f"Task #{task_id} not found or already running")

        except ValueError:
            self.send_response(response_url, "Invalid task ID")
        except Exception as e:
            self.send_response(response_url, f"Failed to cancel task: {str(e)}")
            logger.error(f"Failed to cancel task: {e}")

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

    def handle_credits_command(self, response_url: str):
        """Handle /credits command - shows budget and usage information"""
        try:
            if not self.scheduler:
                self.send_response(response_url, "Scheduler not available")
                return

            credit_status = self.scheduler.get_credit_status()
            window = credit_status["current_window"]
            queue = credit_status["queue"]
            budget = credit_status.get("budget", {})

            # Build budget section
            time_icon = "🌙" if budget.get("is_nighttime") else "☀️"
            time_period = budget.get("time_period", "unknown")
            budget_section = ""
            if budget:
                remaining = budget.get("remaining_budget_usd", 0)
                quota = budget.get("current_quota_usd", 0)
                today_total = budget.get("today_total_usage_usd", 0)
                budget_section = (
                    f"{time_icon} {time_period.capitalize()} Budget\n"
                    f"Remaining: ${remaining:.2f} / ${quota:.2f}\n"
                    f"Today Total: ${today_total:.2f}\n"
                    f"\n"
                )

            message = (
                f"💳 Usage & Budget Status\n"
                f"\n"
                f"{budget_section}"
                f"⏱️ Credit Window\n"
                f"Time Remaining: {window['time_remaining_minutes']}m\n"
                f"Tasks Executed: {window['tasks_executed']}\n"
                f"\n"
                f"📋 Queue:\n"
                f"Pending: {queue['pending']}\n"
                f"In Progress: {queue['in_progress']}\n"
                f"Completed: {queue['completed']}\n"
                f"Failed: {queue['failed']}\n"
                f"\n"
                f"⚙️ Capacity: {self.scheduler.get_execution_slots_available()}/{credit_status['max_parallel']} slots available"
            )
            self.send_response(response_url, message)

        except Exception as e:
            self.send_response(response_url, f"Failed to get credit status: {str(e)}")
            logger.error(f"Failed to get credit status: {e}")

    def handle_health_command(self, response_url: str):
        """Handle /health command"""
        try:
            if not self.monitor:
                self.send_response(response_url, "Monitor not available")
                return

            health = self.monitor.check_health()
            status_emoji = {
                "healthy": "✅",
                "degraded": "⚠️",
                "unhealthy": "❌",
            }.get(health["status"], "❓")

            system = health.get("system", {})
            db = health.get("database", {})
            storage = health.get("storage", {})

            message = (
                f"{status_emoji} Status: {health['status'].upper()}\n"
                f"Uptime: {health['uptime_human']}\n"
                f"\n"
                f"🖥️ System:\n"
                f"CPU: {system.get('cpu_percent', 'N/A')}%\n"
                f"Memory: {system.get('memory_percent', 'N/A')}%\n"
                f"\n"
                f"💾 Database:\n"
                f"Size: {db.get('size_mb', 'N/A')} MB\n"
                f"Modified: {db.get('modified_ago_seconds', 'N/A')}s ago\n"
                f"\n"
                f"📦 Storage:\n"
                f"Files: {storage.get('count', 'N/A')}\n"
                f"Size: {storage.get('total_size_mb', 'N/A')} MB"
            )
            self.send_response(response_url, message)

        except Exception as e:
            self.send_response(response_url, f"Failed to get health status: {str(e)}")
            logger.error(f"Failed to get health status: {e}")

    def handle_metrics_command(self, response_url: str):
        """Handle /metrics command"""
        try:
            if not self.monitor:
                self.send_response(response_url, "Monitor not available")
                return

            stats = self.monitor.get_stats()

            message = (
                f"📊 Performance Metrics\n"
                f"Uptime: {stats['uptime_human']}\n"
                f"\n"
                f"Tasks:\n"
                f"✓ Completed: {stats['tasks_completed']}\n"
                f"✗ Failed: {stats['tasks_failed']}\n"
                f"Success Rate: {stats['success_rate']:.1f}%\n"
                f"\n"
                f"Timing:\n"
                f"Avg Duration: {stats['avg_processing_time']}s\n"
                f"Total Time: {stats['total_processing_time']}s"
            )
            self.send_response(response_url, message)

        except Exception as e:
            self.send_response(response_url, f"Failed to get metrics: {str(e)}")
            logger.error(f"Failed to get metrics: {e}")
