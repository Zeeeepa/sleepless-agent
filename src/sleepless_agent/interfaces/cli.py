"""Command line interface for Sleepless Agent."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from loguru import logger

from sleepless_agent.config import get_config
from sleepless_agent.core import TaskPriority, TaskQueue, init_db
from sleepless_agent.core.task_utils import parse_task_description, slugify_project
from sleepless_agent.monitoring.monitor import HealthMonitor
from sleepless_agent.monitoring.report_generator import ReportGenerator


@dataclass
class CLIContext:
    """Holds shared resources for CLI commands."""

    task_queue: TaskQueue
    monitor: HealthMonitor
    report_generator: ReportGenerator
    db_path: Path
    results_path: Path
    logs_dir: Path


def build_context(args: argparse.Namespace) -> CLIContext:
    """Create the CLI context using config values."""

    config = get_config()

    db_path = Path(config.agent.db_path)
    results_path = Path(config.agent.results_path)
    logs_dir = Path("./logs")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    # Ensure database schema exists before instantiating the queue
    init_db(str(db_path))

    queue = TaskQueue(str(db_path))
    monitor = HealthMonitor(str(db_path), str(results_path))
    report_generator = ReportGenerator(base_path=str(db_path.parent / "reports"))

    return CLIContext(
        task_queue=queue,
        monitor=monitor,
        report_generator=report_generator,
        db_path=db_path,
        results_path=results_path,
        logs_dir=logs_dir,
    )




def command_task(ctx: CLIContext, description: str, priority: TaskPriority, project_name: Optional[str] = None) -> int:
    """Create a task with the given priority."""

    description = description.strip()
    if not description:
        print("Description cannot be empty", file=sys.stderr)
        return 1

    description, parsed_project, note = parse_task_description(description)

    # Prefer argparse --project flag over parsed one
    final_project_name = project_name or parsed_project

    # Generate project_id from project_name (simple slug)
    project_id = None
    if final_project_name:
        project_id = slugify_project(final_project_name)

    task = ctx.task_queue.add_task(
        description=description,
        priority=priority,
        project_id=project_id,
        project_name=final_project_name,
    )
    if priority == TaskPriority.SERIOUS:
        label = "Serious"
    elif priority == TaskPriority.RANDOM:
        label = "Thought"
    else:
        label = "Generated"
    project_info = f" [Project: {final_project_name}]" if final_project_name else ""
    print(f"{label} task #{task.id} queued{project_info}:\n{description}")
    if note:
        print(note, file=sys.stderr)
    return 0


def command_status(ctx: CLIContext) -> int:
    """Print comprehensive system status (health + metrics + queue + budget)."""

    # System health check
    health = ctx.monitor.check_health()
    status_emoji = {
        "healthy": "✅",
        "degraded": "⚠️",
        "unhealthy": "❌",
    }.get(health["status"], "❓")

    system = health.get("system", {})
    db = health.get("database", {})
    storage = health.get("storage", {})

    print(f"\n{status_emoji} System Status: {health['status'].upper()}")
    print(f"⏱️  Uptime: {health['uptime_human']}")
    print(f"🖥️  CPU: {system.get('cpu_percent', 'N/A')}%")
    print(f"💾 Memory: {system.get('memory_percent', 'N/A')}%")

    # Queue status
    queue_status = ctx.task_queue.get_queue_status()
    print(f"\n📊 Queue Status")
    print(f"  Total      : {queue_status['total']}")
    print(f"  Pending    : {queue_status['pending']}")
    print(f"  In Progress: {queue_status['in_progress']}")
    print(f"  Completed  : {queue_status['completed']}")
    print(f"  Failed     : {queue_status['failed']}")

    # All-time metrics
    entries = _load_metrics(ctx.logs_dir)
    if entries:
        total = len(entries)
        successes = sum(1 for e in entries if e.get("success"))
        failures = total - successes
        success_rate = (successes / total * 100) if total > 0 else 0
        avg_duration = 0.0
        durations = [e.get("duration_seconds", 0) for e in entries if isinstance(e.get("duration_seconds"), (int, float))]
        if durations:
            avg_duration = sum(durations) / len(durations)

        print(f"\n📈 Performance (All-Time)")
        print(f"  Total Tasks: {total}")
        print(f"  Success Rate: {success_rate:.1f}% ({successes} ✓ / {failures} ✗)")
        print(f"  Avg Duration: {avg_duration:.1f}s")

    # Time-window metrics
    cutoff = datetime.utcnow() - timedelta(hours=24)
    recent = []
    for entry in entries:
        timestamp = entry.get("timestamp")
        if not timestamp:
            continue
        try:
            ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            continue
        if ts >= cutoff:
            recent.append(entry)

    if recent:
        recent_successes = sum(1 for e in recent if e.get("success"))
        print(f"\n⏰ Recent Activity (Last 24h)")
        print(f"  Tasks Executed: {len(recent)}")
        print(f"  Success Rate: {recent_successes / len(recent) * 100:.1f}% ({recent_successes} ✓ / {len(recent) - recent_successes} ✗)")

    # Storage info
    print(f"\n💿 Storage")
    if db:
        print(f"  Database: {db.get('size_mb', 'N/A')} MB (modified {db.get('modified_ago_seconds', 'N/A')}s ago)")
    if storage:
        print(f"  Results: {storage.get('count', 'N/A')} files ({storage.get('total_size_mb', 'N/A')} MB)")

    # Projects info
    projects = ctx.task_queue.get_projects()
    if projects:
        print(f"\n📦 Projects")
        for proj in projects:
            proj_id = proj['project_id']
            proj_name = proj['project_name']
            total = proj['total_tasks']
            pending = proj['pending']
            in_progress = proj['in_progress']

            status_parts = []
            if pending > 0:
                status_parts.append(f"{pending} pending")
            if in_progress > 0:
                status_parts.append(f"{in_progress} in_progress")
            status = ", ".join(status_parts) or "idle"

            print(f"  {proj_id:<20} {proj_name:<20} {total:>6} tasks ({status})")

    print()
    return 0


def command_cancel(ctx: CLIContext, identifier: str | int) -> int:
    """Cancel a pending task or move a project to trash.

    If identifier is a task ID (integer), cancels that task and moves it to trash.
    If identifier is a project name/ID (string), moves the project and all its tasks to trash.
    Nothing is permanently deleted - everything goes to workspace/trash/.
    """

    # Try to parse as integer (task ID)
    if isinstance(identifier, int):
        task_id = identifier
        task = ctx.task_queue.cancel_task(task_id)
        if not task:
            print(f"Task #{task_id} not found or already running", file=sys.stderr)
            return 1
        print(f"Task #{task_id} moved to trash")
        return 0

    # Try to interpret as project ID
    identifier_str = str(identifier)
    try:
        # Check if it's an integer string
        task_id = int(identifier_str)
        task = ctx.task_queue.cancel_task(task_id)
        if not task:
            print(f"Task #{task_id} not found or already running", file=sys.stderr)
            return 1
        print(f"Task #{task_id} moved to trash")
        return 0
    except ValueError:
        # It's a project identifier, handle project soft deletion
        project_id = _slugify_project(identifier_str)
        project = ctx.task_queue.get_project_by_id(project_id)

        if not project:
            print(f"Project not found: {identifier_str} (slug: {project_id})", file=sys.stderr)
            return 1

        # Confirm move to trash
        print(f"About to move project '{project['project_name']}' ({project_id}) to trash")
        print(f"This will move {project['total_tasks']} task(s) to trash")
        print(f"Workspace will be moved to: workspace/trash/project_{project_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}/")

        response = input("Continue? (y/N): ").strip().lower()
        if response != 'y':
            print("Cancelled")
            return 0

        # Soft delete tasks from database
        count = ctx.task_queue.delete_project(project_id)
        print(f"Moved {count} task(s) to trash in database")

        # Move workspace directory to trash
        workspace_path = Path("workspace") / "projects" / project_id
        if workspace_path.exists():
            trash_dir = Path("workspace") / "trash"
            trash_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            trash_path = trash_dir / f"project_{project_id}_{timestamp}"
            workspace_path.rename(trash_path)
            print(f"Moved workspace to trash: {trash_path}")
        else:
            print(f"Workspace directory not found: {workspace_path} (no workspace to move)")

        return 0


def _load_metrics(logs_dir: Path) -> list[dict]:
    """Load metrics entries from metrics.jsonl if available."""

    metrics_file = logs_dir / "metrics.jsonl"
    if not metrics_file.exists():
        return []

    entries: list[dict] = []
    with metrics_file.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:  # pragma: no cover - log noise
                logger.warning("Failed to parse metrics line: {}", line)
    return entries




def _slugify_project(identifier: str) -> str:
    """Convert project name/id to slugified project_id (auto-detect)."""
    return re.sub(r'[^a-z0-9-]', '-', identifier.lower())


def command_trash(ctx: CLIContext, subcommand: Optional[str] = None, identifier: Optional[str] = None) -> int:
    """Manage trash (list, restore, empty)."""

    if not subcommand:
        subcommand = "list"

    if subcommand == "list":
        trash_dir = Path("workspace") / "trash"
        if not trash_dir.exists():
            print("🗑️  Trash is empty")
            return 0

        items = list(trash_dir.iterdir())
        if not items:
            print("🗑️  Trash is empty")
            return 0

        print("🗑️  Trash Contents:")
        for item in sorted(items):
            if item.is_dir():
                size_mb = sum(f.stat().st_size for f in item.rglob("*") if f.is_file()) / (1024 * 1024)
                print(f"  📁 {item.name} ({size_mb:.1f} MB)")
        return 0

    elif subcommand == "restore":
        if not identifier:
            print("Usage: sleepless trash restore <project_id_or_name>", file=sys.stderr)
            return 1

        trash_dir = Path("workspace") / "trash"
        if not trash_dir.exists():
            print("🗑️  Trash is empty", file=sys.stderr)
            return 1

        # Find matching item in trash
        search_term = identifier.lower().replace(" ", "-")
        matching_items = [item for item in trash_dir.iterdir() if search_term in item.name.lower()]

        if not matching_items:
            print(f"Project not found in trash: {identifier}", file=sys.stderr)
            return 1

        if len(matching_items) > 1:
            print(f"Multiple matches found for '{identifier}'. Be more specific:", file=sys.stderr)
            for item in matching_items:
                print(f"  - {item.name}", file=sys.stderr)
            return 1

        trash_item = matching_items[0]

        # Extract project_id from trash item name (e.g., "project_myapp_20231015_120000")
        parts = trash_item.name.split("_")
        if parts[0] != "project":
            print(f"Invalid trash item format: {trash_item.name}", file=sys.stderr)
            return 1

        # Reconstruct project_id (everything except the last timestamp)
        project_id = "_".join(parts[1:-2])  # Remove "project" prefix and timestamp parts

        # Restore workspace
        workspace_path = Path("workspace") / "projects" / project_id
        if workspace_path.exists():
            print(f"Workspace already exists at {workspace_path}", file=sys.stderr)
            response = input("Overwrite? (y/N): ").strip().lower()
            if response != 'y':
                print("Cancelled")
                return 0
            shutil.rmtree(workspace_path)

        trash_item.rename(workspace_path)
        print(f"✅ Restored project '{project_id}' from trash")

        # Note: Tasks remain in CANCELLED status - user would need to manually update them
        print("⚠️  Note: Tasks remain in CANCELLED status. Update them manually if needed.")
        return 0

    elif subcommand == "empty":
        trash_dir = Path("workspace") / "trash"
        if not trash_dir.exists() or not list(trash_dir.iterdir()):
            print("🗑️  Trash is already empty")
            return 0

        print("About to permanently delete all items in trash")
        response = input("Continue? (y/N): ").strip().lower()
        if response != 'y':
            print("Cancelled")
            return 0

        count = 0
        for item in trash_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
                count += 1

        print(f"✅ Deleted {count} item(s) from trash")
        return 0

    else:
        print(f"Unknown trash subcommand: {subcommand}", file=sys.stderr)
        print("Usage: sleepless trash list|restore|empty [identifier]", file=sys.stderr)
        return 1


def command_report(ctx: CLIContext, identifier: Optional[str] = None, list_reports: bool = False) -> int:
    """Unified report command - shows task details, daily reports, or project reports.

    Usage:
        sleepless report              # Today's daily report
        sleepless report 123          # Task #123 details
        sleepless report 2025-10-22   # Specific date's report
        sleepless report project-id   # Project report
        sleepless report --list       # List all reports
    """

    if list_reports:
        # List all reports
        daily_reports = ctx.report_generator.list_daily_reports()
        project_reports = ctx.report_generator.list_project_reports()

        if daily_reports:
            print("📅 Daily Reports:")
            for report_date in daily_reports:
                print(f"  • {report_date}")
        else:
            print("📅 No daily reports available")

        if project_reports:
            print("\n📦 Project Reports:")
            for project_id in project_reports:
                print(f"  • {project_id}")
        else:
            if daily_reports:
                print("\n📦 No project reports available")
            else:
                print("📦 No project reports available")

        return 0

    if not identifier:
        # Default: today's daily report
        date = datetime.utcnow().strftime("%Y-%m-%d")
        report = ctx.report_generator.get_daily_report(date)
        print(report)
        return 0

    # Auto-detect: is it a task ID (integer), date, or project ID?
    # First try to parse as integer (task ID)
    try:
        task_id = int(identifier)
        # It's a task ID, show task details
        task = ctx.task_queue.get_task(task_id)
        if not task:
            print(f"Task #{task_id} not found", file=sys.stderr)
            return 1

        print(f"Task #{task.id}")
        print(f"  Status  : {task.status.value}")
        print(f"  Priority: {task.priority.value}")
        print(f"  Created : {task.created_at}")
        if task.error_message:
            print(f"  Error   : {task.error_message}")
        if task.context:
            print("  Context :")
            try:
                context = json.loads(task.context)
                print(json.dumps(context, indent=2))
            except json.JSONDecodeError:
                print(f"    {task.context}")
        return 0
    except ValueError:
        pass

    # Try to parse as date (YYYY-MM-DD)
    try:
        datetime.strptime(identifier, "%Y-%m-%d")
        # It's a date
        report = ctx.report_generator.get_daily_report(identifier)
        print(report)
        return 0
    except ValueError:
        # Not a date, treat as project ID
        report = ctx.report_generator.get_project_report(identifier)
        print(report)
        return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser."""

    parser = argparse.ArgumentParser(description="Sleepless Agent command line interface")

    subparsers = parser.add_subparsers(dest="command", required=True)

    task_parser = subparsers.add_parser("task", help="Queue a serious task")
    task_parser.add_argument("description", nargs=argparse.REMAINDER, help="Task description")
    task_parser.add_argument("-p", "--project", help="Project name to associate with the task")

    think_parser = subparsers.add_parser("think", help="Capture a random thought")
    think_parser.add_argument("description", nargs=argparse.REMAINDER, help="Thought description")
    think_parser.add_argument("-p", "--project", help="Project name to associate with the thought")

    status_parser = subparsers.add_parser("status", help="Show comprehensive system status (health + metrics + queue)")

    cancel_parser = subparsers.add_parser("cancel", help="Move a task or project to trash")
    cancel_parser.add_argument("identifier", help="Task ID (integer) or project name/ID (string)")

    # Report command - unified for daily/project reports
    report_parser = subparsers.add_parser("report", help="Show task details, daily reports, or project reports (auto-detect)")
    report_parser.add_argument("identifier", nargs="?", help="Task ID (integer), report date (YYYY-MM-DD), or project ID (default: today)")
    report_parser.add_argument("--list", dest="list_reports", action="store_true", help="List all available reports")

    # Trash command - manage deleted items
    trash_parser = subparsers.add_parser("trash", help="Manage trash (list, restore, empty)")
    trash_parser.add_argument("subcommand", nargs="?", default="list", help="list (default) | restore | empty")
    trash_parser.add_argument("identifier", nargs="?", help="Project ID or name (for restore)")

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """Main entry point for the CLI."""

    parser = build_parser()
    args = parser.parse_args(argv)

    ctx = build_context(args)

    if args.command == "task":
        description = " ".join(args.description).strip()
        if not description:
            parser.error("task requires a description")
        return command_task(ctx, description, TaskPriority.SERIOUS, args.project)

    if args.command == "think":
        description = " ".join(args.description).strip()
        if not description:
            parser.error("think requires a description")
        return command_task(ctx, description, TaskPriority.RANDOM, args.project)

    if args.command == "status":
        return command_status(ctx)

    if args.command == "cancel":
        return command_cancel(ctx, args.identifier)

    if args.command == "report":
        return command_report(ctx, args.identifier, args.list_reports)

    if args.command == "trash":
        return command_trash(ctx, args.subcommand, args.identifier)

    parser.error(f"Unknown command: {args.command}")
    return 1


if __name__ == "__main__":  # pragma: no cover - manual execution
    sys.exit(main())
