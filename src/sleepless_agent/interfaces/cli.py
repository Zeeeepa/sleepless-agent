"""Command line interface for Sleepless Agent."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from sleepless_agent.config import get_config
from sleepless_agent.core import TaskPriority, TaskQueue, init_db
from sleepless_agent.monitoring.monitor import HealthMonitor


LOGGER = logging.getLogger(__name__)


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


def command_task(ctx: CLIContext, description: str, priority: TaskPriority) -> int:
    """Create a task with the given priority."""

    description = description.strip()
    if not description:
        print("Description cannot be empty", file=sys.stderr)
        return 1

    task = ctx.task_queue.add_task(description=description, priority=priority)
    label = "Serious" if priority == TaskPriority.SERIOUS else "Thought"
    print(f"{label} task #{task.id} queued:\n{description}")
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
                LOGGER.warning("Failed to parse metrics line: %s", line)
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


def build_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser."""

    parser = argparse.ArgumentParser(description="Sleepless Agent command line interface")
    add_common_arguments(parser)

    subparsers = parser.add_subparsers(dest="command", required=True)

    task_parser = subparsers.add_parser("task", help="Queue a serious task")
    task_parser.add_argument("description", nargs=argparse.REMAINDER, help="Task description")

    think_parser = subparsers.add_parser("think", help="Capture a random thought")
    think_parser.add_argument("description", nargs=argparse.REMAINDER, help="Thought description")

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

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    """Main entry point for the CLI."""

    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO)

    ctx = build_context(args)

    if args.command == "task":
        description = " ".join(args.description).strip()
        if not description:
            parser.error("task requires a description")
        return command_task(ctx, description, TaskPriority.SERIOUS)

    if args.command == "think":
        description = " ".join(args.description).strip()
        if not description:
            parser.error("think requires a description")
        return command_task(ctx, description, TaskPriority.RANDOM)

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

    parser.error(f"Unknown command: {args.command}")
    return 1


if __name__ == "__main__":  # pragma: no cover - manual execution
    sys.exit(main())
