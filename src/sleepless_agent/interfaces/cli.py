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
from sleepless_agent.monitoring.monitor import HealthMonitor


@dataclass
class CLIContext:
    """Holds shared resources for CLI commands."""

    task_queue: TaskQueue
    monitor: HealthMonitor
    db_path: Path
    results_path: Path
    logs_dir: Path


def build_context(args: argparse.Namespace) -> CLIContext:
    """Create the CLI context using config defaults with optional overrides."""

    config = get_config()

    db_path = Path(args.db_path or config.agent.db_path)
    results_path = Path(args.results_path or config.agent.results_path)
    logs_dir = Path(args.logs_dir or "./logs")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    # Ensure database schema exists before instantiating the queue
    init_db(str(db_path))

    queue = TaskQueue(str(db_path))
    monitor = HealthMonitor(str(db_path), str(results_path))

    return CLIContext(
        task_queue=queue,
        monitor=monitor,
        db_path=db_path,
        results_path=results_path,
        logs_dir=logs_dir,
    )


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    """Add arguments shared by all commands."""

    parser.add_argument(
        "--db-path",
        help="Path to the tasks SQLite database (default: from config)",
    )
    parser.add_argument(
        "--results-path",
        help="Directory that stores task results (default: from config)",
    )
    parser.add_argument(
        "--logs-dir",
        help="Directory containing agent logs (default: ./logs)",
    )


def command_task(ctx: CLIContext, description: str, priority: TaskPriority, project_name: Optional[str] = None) -> int:
    """Create a task with the given priority."""

    description = description.strip()
    if not description:
        print("Description cannot be empty", file=sys.stderr)
        return 1

    # Parse --project=<name> from description (for consistency with bot)
    import re
    parsed_project = None
    if "--project=" in description:
        match = re.search(r'--project=(\S+)', description)
        if match:
            parsed_project = match.group(1)
            description = description.replace(f"--project={parsed_project}", "").strip()

    # Prefer argparse --project flag over parsed one
    final_project_name = project_name or parsed_project

    # Generate project_id from project_name (simple slug)
    project_id = None
    if final_project_name:
        project_id = re.sub(r'[^a-z0-9-]', '-', final_project_name.lower())

    task = ctx.task_queue.add_task(
        description=description,
        priority=priority,
        project_id=project_id,
        project_name=final_project_name,
    )
    label = "Serious" if priority == TaskPriority.SERIOUS else "Thought"
    project_info = f" [Project: {final_project_name}]" if final_project_name else ""
    print(f"{label} task #{task.id} queued{project_info}:\n{description}")
    return 0


def command_status(ctx: CLIContext) -> int:
    """Print queue summary."""

    status = ctx.task_queue.get_queue_status()
    print("Queue status:")
    print(f"  Total      : {status['total']}")
    print(f"  Pending    : {status['pending']}")
    print(f"  In Progress: {status['in_progress']}")
    print(f"  Completed  : {status['completed']}")
    print(f"  Failed     : {status['failed']}")
    return 0


def command_results(ctx: CLIContext, task_id: int) -> int:
    """Display results for a task."""

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


def command_priority(ctx: CLIContext, task_id: int, priority: str) -> int:
    """Update task priority."""

    wanted = TaskPriority.SERIOUS if priority == "serious" else TaskPriority.RANDOM
    task = ctx.task_queue.update_priority(task_id, wanted)
    if not task:
        print(f"Task #{task_id} not found", file=sys.stderr)
        return 1

    print(f"Task #{task_id} priority set to {wanted.value}")
    return 0


def command_cancel(ctx: CLIContext, task_id: int) -> int:
    """Cancel a pending task."""

    task = ctx.task_queue.cancel_task(task_id)
    if not task:
        print(f"Task #{task_id} not found or already running", file=sys.stderr)
        return 1

    print(f"Task #{task_id} cancelled")
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


def command_credits(ctx: CLIContext, window_hours: int) -> int:
    """Show credit usage based on recent metrics."""

    entries = _load_metrics(ctx.logs_dir)
    cutoff = datetime.utcnow() - timedelta(hours=window_hours)

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

    status = ctx.task_queue.get_queue_status()
    print("Credit window summary (last %d hours):" % window_hours)
    print(f"  Tasks executed: {len(recent)}")
    successes = sum(1 for e in recent if e.get("success"))
    print(f"  Successful    : {successes}")
    print(f"  Failed        : {len(recent) - successes}")
    print("\nQueue snapshot:")
    print(f"  Pending       : {status['pending']}")
    print(f"  In Progress   : {status['in_progress']}")
    print(f"  Completed     : {status['completed']}")
    print(f"  Failed        : {status['failed']}")
    return 0


def command_health(ctx: CLIContext) -> int:
    """Run health checks."""

    report = ctx.monitor.check_health()
    print(f"Status    : {report['status'].upper()}")
    print(f"Uptime    : {report['uptime_human']}")
    system = report.get("system", {})
    print(f"CPU       : {system.get('cpu_percent', 'N/A')}%")
    print(f"Memory    : {system.get('memory_percent', 'N/A')}%")
    db = report.get("database", {})
    if db:
        print("Database :")
        print(f"  Path    : {ctx.db_path}")
        print(f"  Size    : {db.get('size_mb', 'N/A')} MB")
        print(f"  Modified: {db.get('modified_ago_seconds', 'N/A')}s ago")
    storage = report.get("storage", {})
    if storage:
        print("Results  :")
        print(f"  Path    : {ctx.results_path}")
        print(f"  Files   : {storage.get('count', 'N/A')}")
        print(f"  Size    : {storage.get('total_size_mb', 'N/A')} MB")
    return 0


def command_metrics(ctx: CLIContext) -> int:
    """Print aggregated metrics from history."""

    entries = _load_metrics(ctx.logs_dir)
    if not entries:
        print("No metrics available (logs/metrics.jsonl missing)")
        return 0

    total = len(entries)
    successes = sum(1 for e in entries if e.get("success"))
    failures = total - successes
    avg_duration = 0.0
    durations = [e.get("duration_seconds", 0) for e in entries if isinstance(e.get("duration_seconds"), (int, float))]
    if durations:
        avg_duration = sum(durations) / len(durations)

    first_ts = entries[0].get("timestamp")
    last_ts = entries[-1].get("timestamp")

    print("Metrics history:")
    print(f"  Entries     : {total}")
    print(f"  Successful  : {successes}")
    print(f"  Failed      : {failures}")
    print(f"  Avg Duration: {avg_duration:.1f}s")
    if first_ts and last_ts:
        print(f"  Range       : {first_ts} – {last_ts}")
    return 0


def _slugify_project(identifier: str) -> str:
    """Convert project name/id to slugified project_id (auto-detect)."""
    return re.sub(r'[^a-z0-9-]', '-', identifier.lower())


def command_ls(ctx: CLIContext) -> int:
    """List all projects with task counts and status."""

    projects = ctx.task_queue.get_projects()
    if not projects:
        print("No projects found")
        return 0

    print("Projects:")
    print(f"{'ID':<20} {'Name':<20} {'Tasks':>6} {'Status':<20}")
    print("-" * 70)

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

        print(f"{proj_id:<20} {proj_name:<20} {total:>6} {status:<20}")

    return 0


def command_cat(ctx: CLIContext, identifier: str) -> int:
    """Show detailed project information."""

    project_id = _slugify_project(identifier)
    project = ctx.task_queue.get_project_by_id(project_id)

    if not project:
        print(f"Project not found: {identifier} (slug: {project_id})", file=sys.stderr)
        return 1

    print(f"Project: {project['project_name']} ({project['project_id']})")
    print(f"Workspace: workspace/project_{project['project_id']}/")
    print(f"Tasks: {project['total_tasks']} total")
    print(f"  - Pending    : {project['pending']}")
    print(f"  - In Progress: {project['in_progress']}")
    print(f"  - Completed  : {project['completed']}")
    print(f"  - Failed     : {project['failed']}")
    print(f"Created: {project['created_at']}")

    if project['tasks']:
        print("\nRecent tasks:")
        for task in project['tasks']:
            status_icon = {
                'completed': '✓',
                'in_progress': '→',
                'pending': '○',
                'failed': '✗',
                'cancelled': '◌',
            }.get(task['status'], '?')
            print(f"  {status_icon} #{task['id']} [{task['status']}] {task['description']}")

    return 0


def command_rm(ctx: CLIContext, identifier: str, keep_workspace: bool = False) -> int:
    """Delete a project and optionally its workspace."""

    project_id = _slugify_project(identifier)
    project = ctx.task_queue.get_project_by_id(project_id)

    if not project:
        print(f"Project not found: {identifier} (slug: {project_id})", file=sys.stderr)
        return 1

    # Confirm deletion
    print(f"About to delete project '{project['project_name']}' ({project_id})")
    print(f"This will delete {project['total_tasks']} task(s)")

    if not keep_workspace:
        print(f"Workspace will be deleted: workspace/project_{project_id}/")
    else:
        print(f"Workspace will be kept: workspace/project_{project_id}/")

    response = input("Continue? (y/N): ").strip().lower()
    if response != 'y':
        print("Cancelled")
        return 0

    # Delete tasks from database
    count = ctx.task_queue.delete_project(project_id)
    print(f"Deleted {count} task(s) from database")

    # Optionally delete workspace directory
    if not keep_workspace:
        workspace_path = Path("workspace") / f"project_{project_id}"
        if workspace_path.exists():
            shutil.rmtree(workspace_path)
            print(f"Deleted workspace directory: {workspace_path}")
        else:
            print(f"Workspace directory not found: {workspace_path}")

    return 0


def build_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser."""

    parser = argparse.ArgumentParser(description="Sleepless Agent command line interface")
    add_common_arguments(parser)

    subparsers = parser.add_subparsers(dest="command", required=True)

    task_parser = subparsers.add_parser("task", help="Queue a serious task")
    task_parser.add_argument("description", nargs=argparse.REMAINDER, help="Task description")
    task_parser.add_argument("-p", "--project", help="Project name to associate with the task")

    think_parser = subparsers.add_parser("think", help="Capture a random thought")
    think_parser.add_argument("description", nargs=argparse.REMAINDER, help="Thought description")
    think_parser.add_argument("-p", "--project", help="Project name to associate with the thought")

    subparsers.add_parser("status", help="Show queue status")

    results_parser = subparsers.add_parser("results", help="Show task details")
    results_parser.add_argument("task_id", type=int)

    priority_parser = subparsers.add_parser("priority", help="Update task priority")
    priority_parser.add_argument("task_id", type=int)
    priority_parser.add_argument("priority", choices=["random", "serious"])

    cancel_parser = subparsers.add_parser("cancel", help="Cancel a pending task")
    cancel_parser.add_argument("task_id", type=int)

    credits_parser = subparsers.add_parser("credits", help="Show credit window summary")
    credits_parser.add_argument(
        "--hours",
        type=int,
        default=5,
        help="Window size in hours to inspect (default: 5)",
    )

    subparsers.add_parser("health", help="Run health checks")
    subparsers.add_parser("metrics", help="Show aggregated performance metrics")

    # Project management commands
    subparsers.add_parser("ls", help="List all projects")

    cat_parser = subparsers.add_parser("cat", help="Show project details")
    cat_parser.add_argument("project", help="Project ID or name")

    rm_parser = subparsers.add_parser("rm", help="Delete a project")
    rm_parser.add_argument("project", help="Project ID or name")
    rm_parser.add_argument(
        "--keep-workspace",
        action="store_true",
        help="Keep workspace directory when deleting project",
    )

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

    if args.command == "results":
        return command_results(ctx, args.task_id)

    if args.command == "priority":
        return command_priority(ctx, args.task_id, args.priority)

    if args.command == "cancel":
        return command_cancel(ctx, args.task_id)

    if args.command == "credits":
        return command_credits(ctx, args.hours)

    if args.command == "health":
        return command_health(ctx)

    if args.command == "metrics":
        return command_metrics(ctx)

    if args.command == "ls":
        return command_ls(ctx)

    if args.command == "cat":
        return command_cat(ctx, args.project)

    if args.command == "rm":
        return command_rm(ctx, args.project, args.keep_workspace)

    parser.error(f"Unknown command: {args.command}")
    return 1


if __name__ == "__main__":  # pragma: no cover - manual execution
    sys.exit(main())
