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
from rich import box
from rich.align import Align
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from sleepless_agent.config import get_config
from sleepless_agent.core import TaskPriority, TaskQueue, init_db
from sleepless_agent.core.models import TaskStatus
from sleepless_agent.core.display import format_age_seconds, format_duration, relative_time, shorten
from sleepless_agent.core.live_status import LiveStatusTracker
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
    logs_dir = db_path.parent  # Use same directory as db_path for metrics

    db_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.mkdir(parents=True, exist_ok=True)

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


def command_check(ctx: CLIContext) -> int:
    """Render an enriched system snapshot."""

    console = Console()

    health = ctx.monitor.check_health()
    queue_status = ctx.task_queue.get_queue_status()
    entries = _load_metrics(ctx.logs_dir)
    metrics_summary = _summarize_metrics(entries)

    status = health.get("status", "unknown")
    status_lower = str(status).lower()
    status_emoji = {
        "healthy": "✅",
        "degraded": "⚠️",
        "unhealthy": "❌",
    }.get(status_lower, "❔")
    status_style = {
        "healthy": "green",
        "degraded": "yellow",
        "unhealthy": "red",
    }.get(status_lower, "grey50")

    system = health.get("system", {})
    db = health.get("database", {})
    storage = health.get("storage", {})

    health_table = Table.grid(padding=(0, 2))
    health_table.add_column(justify="right", style="bold cyan")
    health_table.add_column(justify="left")
    health_table.add_row("Status", f"{status_emoji} [bold]{str(status).upper()}[/]")
    health_table.add_row("Uptime", health.get("uptime_human", "N/A"))
    health_table.add_row("CPU", f"{system.get('cpu_percent', 'N/A')}%")
    health_table.add_row("Memory", f"{system.get('memory_percent', 'N/A')}%")
    health_table.add_row("Queue Depth", f"{queue_status['pending']} pending / {queue_status['in_progress']} running")

    storage_table = Table.grid(padding=(0, 2))
    storage_table.add_column(justify="right", style="bold cyan")
    storage_table.add_column(justify="left")
    if db:
        storage_table.add_row(
            "Database",
            f"{db.get('size_mb', 'N/A')} MB · {format_age_seconds(db.get('modified_ago_seconds'))}",
        )
    else:
        storage_table.add_row("Database", "—")
    if storage:
        storage_table.add_row(
            "Results",
            f"{storage.get('count', 'N/A')} files · {storage.get('total_size_mb', 'N/A')} MB",
        )
    else:
        storage_table.add_row("Results", "—")

    health_panel = Panel(health_table, title="System Health", border_style=status_style)
    storage_panel = Panel(storage_table, title="Storage", border_style="cyan")

    queue_table = Table(box=box.ROUNDED, expand=True, title="Queue Summary")
    queue_table.add_column("State", style="bold cyan")
    queue_table.add_column("Count", justify="right", style="bold")
    queue_table.add_row("Pending", str(queue_status["pending"]))
    queue_table.add_row("In Progress", str(queue_status["in_progress"]))
    queue_table.add_row("Completed", str(queue_status["completed"]))
    queue_table.add_row("Failed", str(queue_status["failed"]))
    queue_table.add_row("Total", str(queue_status["total"]))
    queue_panel = Panel(queue_table, border_style="blue")

    metrics_table = Table(box=box.ROUNDED, expand=True, title="Performance")
    metrics_table.add_column("Window", style="bold cyan")
    metrics_table.add_column("Tasks", justify="right")
    metrics_table.add_column("Success", justify="right")
    metrics_table.add_column("Error", justify="right", style="red")
    metrics_table.add_column("Avg Time", justify="right")

    if metrics_summary["total"]:
        success_rate = metrics_summary["success_rate"]
        error_rate = 100 - success_rate if success_rate is not None else None
        success_style = "green" if success_rate and success_rate >= 80 else "yellow" if success_rate and success_rate >= 50 else "red"
        metrics_table.add_row(
            "All-Time",
            str(metrics_summary["total"]),
            f"[{success_style}]{success_rate:.1f}%[/]" if success_rate is not None else "—",
            f"{error_rate:.1f}%" if error_rate is not None else "—",
            format_duration(metrics_summary["avg_duration"]),
        )
    else:
        metrics_table.add_row("All-Time", "0", "—", "—", "—")

    if metrics_summary["recent_total"]:
        recent_rate = metrics_summary["recent_success_rate"]
        recent_error_rate = 100 - recent_rate if recent_rate is not None else None
        recent_style = "green" if recent_rate and recent_rate >= 80 else "yellow" if recent_rate and recent_rate >= 50 else "red"
        metrics_table.add_row(
            "Last 24h",
            str(metrics_summary["recent_total"]),
            f"[{recent_style}]{recent_rate:.1f}%[/]" if recent_rate is not None else "—",
            f"{recent_error_rate:.1f}%" if recent_error_rate is not None else "—",
            format_duration(metrics_summary["recent_avg_duration"]),
        )
    else:
        metrics_table.add_row("Last 24h", "0", "—", "—", "—")

    metrics_panel = Panel(metrics_table, border_style="yellow")

    live_entries = []
    try:
        tracker = LiveStatusTracker(ctx.db_path.parent / "live_status.json")
        live_entries = tracker.entries()
    except Exception as exc:  # pragma: no cover - best effort
        logger.debug(f"Live status unavailable: {exc}")
        live_entries = []

    live_table = Table(
        box=box.MINIMAL_DOUBLE_HEAD,
        expand=True,
        title=f"Live Sessions ({len(live_entries)})",
    )
    live_table.add_column("Task", style="bold")
    live_table.add_column("Phase", style="cyan")
    live_table.add_column("Query", overflow="fold")
    live_table.add_column("Answer", overflow="fold")
    live_table.add_column("Updated", justify="right")

    for entry in live_entries:
        updated_dt = _parse_timestamp(entry.updated_at)
        updated_text = relative_time(updated_dt) if updated_dt else "—"
        live_table.add_row(
            f"#{entry.task_id}",
            entry.phase.title(),
            shorten(entry.prompt_preview, limit=60) if entry.prompt_preview else "—",
            shorten(entry.answer_preview, limit=60) if entry.answer_preview else "—",
            updated_text,
        )

    if live_entries:
        live_panel = Panel(live_table, border_style="bright_cyan")
    else:
        live_panel = Panel(
            Align.center(Text("No active Claude sessions.", style="dim")),
            title="Live Sessions",
            border_style="bright_cyan",
        )

    running_tasks = ctx.task_queue.get_in_progress_tasks()
    running_table = Table(
        box=box.MINIMAL_DOUBLE_HEAD,
        expand=True,
        title=f"Active Tasks ({len(running_tasks)})",
    )
    running_table.add_column("ID", style="bold")
    running_table.add_column("Project", style="cyan")
    running_table.add_column("Description", overflow="fold")
    running_table.add_column("Owner")
    running_table.add_column("Started")
    running_table.add_column("Elapsed", justify="right")

    now = datetime.utcnow()
    for task in running_tasks:
        elapsed = None
        elapsed_str = "—"
        if task.started_at:
            elapsed = (now - task.started_at).total_seconds()
            # Color-code based on duration: green < 30m, yellow < 1h, red >= 1h
            if elapsed < 1800:  # < 30 minutes
                elapsed_str = f"[green]{format_duration(elapsed)}[/]"
            elif elapsed < 3600:  # < 1 hour
                elapsed_str = f"[yellow]{format_duration(elapsed)}[/]"
            else:  # >= 1 hour (warning!)
                elapsed_str = f"[red bold]⚠️ {format_duration(elapsed)}[/]"
        running_table.add_row(
            str(task.id),
            task.project_name or task.project_id or "—",
            shorten(task.description),
            task.assigned_to or "—",
            task.started_at.isoformat(sep=" ", timespec="minutes") if task.started_at else "—",
            elapsed_str,
        )

    if running_tasks:
        running_panel = Panel(running_table, border_style="magenta")
    else:
        running_panel = Panel(
            Align.center(Text("No tasks currently running.", style="dim")),
            title="Active Tasks",
            border_style="magenta",
        )

    pending_tasks = ctx.task_queue.get_pending_tasks(limit=5)
    pending_table = Table(
        box=box.MINIMAL_DOUBLE_HEAD,
        expand=True,
        title=f"Next Up ({len(pending_tasks)} shown)",
    )
    pending_table.add_column("ID", style="bold")
    pending_table.add_column("Priority")
    pending_table.add_column("Project", style="cyan")
    pending_table.add_column("Created")
    pending_table.add_column("Age")
    pending_table.add_column("Summary", overflow="fold")

    for task in pending_tasks:
        # Calculate task age
        age_seconds = (now - task.created_at).total_seconds()
        age_str = relative_time(task.created_at)

        # Color-code age: normal < 1h, yellow < 24h, red >= 24h (stale!)
        if age_seconds < 3600:  # < 1 hour
            age_display = age_str
        elif age_seconds < 86400:  # < 24 hours
            age_display = f"[yellow]{age_str}[/]"
        else:  # >= 24 hours (stale!)
            age_display = f"[red bold]⚠️ {age_str}[/]"

        # Color-code priority
        priority_display = task.priority.value
        if task.priority.value == "serious":
            priority_display = f"[red bold]{task.priority.value}[/]"
        elif task.priority.value == "random":
            priority_display = f"[cyan]{task.priority.value}[/]"
        else:
            priority_display = f"[dim]{task.priority.value}[/]"

        pending_table.add_row(
            str(task.id),
            priority_display,
            task.project_name or task.project_id or "—",
            task.created_at.isoformat(sep=" ", timespec="minutes"),
            age_display,
            shorten(task.description),
        )

    if pending_tasks:
        pending_panel = Panel(pending_table, border_style="green")
    else:
        pending_panel = Panel(
            Align.center(Text("Queue is clear. 🎉", style="dim")),
            title="Next Up",
            border_style="green",
        )

    projects = ctx.task_queue.get_projects()
    project_panel = None
    if projects:
        project_table = Table(
            title=f"Projects ({len(projects)})",
            box=box.ROUNDED,
            expand=True,
        )
        project_table.add_column("Project", style="bold cyan")
        project_table.add_column("Pending", justify="right")
        project_table.add_column("In Progress", justify="right")
        project_table.add_column("Completed", justify="right")
        project_table.add_column("Total", justify="right")

        for proj in projects:
            project_table.add_row(
                proj["project_name"],
                str(proj["pending"]),
                str(proj["in_progress"]),
                str(proj["completed"]),
                str(proj["total_tasks"]),
            )
        project_panel = Panel(project_table, border_style="bright_blue")

    # Recent Errors Section
    failed_tasks = ctx.task_queue.get_failed_tasks(limit=5)
    errors_panel = None
    if failed_tasks:
        errors_table = Table(
            title=f"Recent Errors ({len(failed_tasks)})",
            box=box.SIMPLE_HEAVY,
            expand=True,
        )
        errors_table.add_column("ID", style="bold red")
        errors_table.add_column("When", style="dim")
        errors_table.add_column("Task", overflow="fold")
        errors_table.add_column("Error", overflow="fold", style="red")

        for task in failed_tasks:
            error_preview = shorten(task.error_message, limit=50) if task.error_message else "Unknown error"
            errors_table.add_row(
                str(task.id),
                relative_time(task.created_at),
                shorten(task.description, limit=40),
                error_preview,
            )
        errors_panel = Panel(errors_table, border_style="red")

    recent_tasks = ctx.task_queue.get_recent_tasks(limit=8)
    status_icons = {
        TaskStatus.COMPLETED: "✅",
        TaskStatus.IN_PROGRESS: "🔄",
        TaskStatus.PENDING: "🕒",
        TaskStatus.FAILED: "❌",
        TaskStatus.CANCELLED: "🗑️",
    }
    recent_table = Table(
        title="Recent Activity",
        box=box.SIMPLE_HEAVY,
        expand=True,
    )
    recent_table.add_column("ID", style="bold")
    recent_table.add_column("Status")
    recent_table.add_column("Project", style="cyan")
    recent_table.add_column("When")
    recent_table.add_column("Summary", overflow="fold")

    for task in recent_tasks:
        icon = status_icons.get(task.status, "•")
        # Color-code status
        status_colors = {
            TaskStatus.COMPLETED: "green",
            TaskStatus.IN_PROGRESS: "cyan",
            TaskStatus.PENDING: "yellow",
            TaskStatus.FAILED: "red",
            TaskStatus.CANCELLED: "dim",
        }
        status_color = status_colors.get(task.status, "white")
        recent_table.add_row(
            str(task.id),
            f"[{status_color}]{icon} {task.status.value}[/]",
            task.project_name or task.project_id or "—",
            relative_time(task.created_at),
            shorten(task.description),
        )
    recent_panel = Panel(recent_table, border_style="orange1")

    # Create hierarchical layout with regions
    layout = Layout(name="root")
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="top_section", size=10),
        Layout(name="middle_section", size=12),
        Layout(name="tasks_section"),
    )

    # Header
    layout["header"].update(
        Panel(
            Text("Sleepless Agent Dashboard", style="bold bright_magenta"),
            border_style="bright_magenta",
        )
    )

    # Top section: System Health + Storage
    layout["top_section"].split_row(
        Layout(name="health", ratio=1),
        Layout(name="storage", ratio=1),
    )
    layout["top_section"]["health"].update(health_panel)
    layout["top_section"]["storage"].update(storage_panel)

    # Middle section: Queue + Metrics
    layout["middle_section"].split_row(
        Layout(name="queue", ratio=1),
        Layout(name="metrics", ratio=1),
    )
    layout["middle_section"]["queue"].update(queue_panel)
    layout["middle_section"]["metrics"].update(metrics_panel)

    # Tasks section: Split into dynamic subsections
    tasks_layout = layout["tasks_section"]
    sections: list[tuple[str, Panel]] = [
        ("live_section", live_panel),
        ("running_section", running_panel),
        ("pending_section", pending_panel),
    ]
    if errors_panel:
        sections.append(("errors_section", errors_panel))
    if project_panel:
        sections.append(("projects_section", project_panel))
    sections.append(("recent_section", recent_panel))

    layouts = [Layout(name=name, ratio=1) for name, _ in sections]
    tasks_layout.split_column(*layouts)
    for name, panel in sections:
        tasks_layout[name].update(panel)

    console.print()
    console.print(layout)

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


def _parse_timestamp(timestamp: Optional[str]) -> Optional[datetime]:
    if not timestamp:
        return None
    try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _summarize_metrics(entries: list[dict]) -> dict:
    """Extract aggregate stats from metrics log entries."""
    total = len(entries)
    successes = sum(1 for e in entries if e.get("success"))
    durations = [
        e.get("duration_seconds")
        for e in entries
        if isinstance(e.get("duration_seconds"), (int, float))
    ]
    avg_duration = sum(durations) / len(durations) if durations else None

    cutoff = datetime.utcnow() - timedelta(hours=24)
    recent = []
    for entry in entries:
        ts = _parse_timestamp(entry.get("timestamp"))
        if ts and ts >= cutoff:
            recent.append(entry)

    recent_total = len(recent)
    recent_successes = sum(1 for e in recent if e.get("success"))
    recent_durations = [
        e.get("duration_seconds")
        for e in recent
        if isinstance(e.get("duration_seconds"), (int, float))
    ]
    recent_avg_duration = (
        sum(recent_durations) / len(recent_durations) if recent_durations else None
    )

    def rate(success_count: int, task_count: int) -> Optional[float]:
        if task_count == 0:
            return None
        return success_count / task_count * 100

    return {
        "total": total,
        "success_rate": rate(successes, total),
        "avg_duration": avg_duration,
        "recent_total": recent_total,
        "recent_success_rate": rate(recent_successes, recent_total),
        "recent_avg_duration": recent_avg_duration,
    }




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

    subparsers.add_parser("check", help="Show comprehensive system overview with rich output")

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

    if args.command == "check":
        return command_check(ctx)

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
