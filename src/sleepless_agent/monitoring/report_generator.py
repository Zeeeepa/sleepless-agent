"""Daily report generation system - append-only updates with end-of-day summarization"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List
from dataclasses import dataclass

from loguru import logger


@dataclass
class TaskMetrics:
    """Task metrics for reporting"""
    task_id: int
    description: str
    priority: str
    status: str  # completed, failed, in_progress
    duration_seconds: int
    files_modified: int
    commands_executed: int
    git_info: Optional[str] = None
    error_message: Optional[str] = None
    timestamp: Optional[str] = None


class ReportGenerator:
    """Generate daily reports with real-time appending and end-of-day summarization"""

    def __init__(self, base_path: str = "./data/reports"):
        """Initialize report generator

        Args:
            base_path: Root directory for all reports
        """
        self.base_path = Path(base_path)
        self.daily_dir = self.base_path / "daily"
        self.projects_dir = self.base_path / "projects"
        self.recent_dir = self.base_path / "recent"

        # Create directories
        self.daily_dir.mkdir(parents=True, exist_ok=True)
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self.recent_dir.mkdir(parents=True, exist_ok=True)

    def append_task_completion(self, task_metrics: TaskMetrics, project_id: Optional[str] = None):
        """Append task completion entry to daily report and optional project report

        Args:
            task_metrics: Task metrics to append
            project_id: Optional project ID to also append to project report
        """
        timestamp = task_metrics.timestamp or datetime.utcnow().isoformat()

        # Append to daily report
        self._append_to_daily_report(task_metrics, timestamp)

        # Append to project report if provided
        if project_id:
            self._append_to_project_report(project_id, task_metrics, timestamp)

    def _append_to_daily_report(self, task_metrics: TaskMetrics, timestamp: str):
        """Append entry to today's daily report"""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        report_file = self.daily_dir / f"{today}.md"

        # Ensure header exists
        self._ensure_daily_report_header(report_file, today)

        # Format entry
        status_emoji = "✓" if task_metrics.status == "completed" else "✗"
        entry = self._format_task_entry(task_metrics, status_emoji, timestamp)

        # Append to report (before summary section)
        try:
            content = report_file.read_text()
            # Find summary section and insert before it
            summary_idx = content.find("\n## Summary")
            if summary_idx != -1:
                new_content = content[:summary_idx] + f"\n{entry}" + content[summary_idx:]
            else:
                new_content = content + f"\n{entry}"

            report_file.write_text(new_content)
        except Exception as e:
            logger.error(f"Failed to append to daily report: {e}")

    def _append_to_project_report(self, project_id: str, task_metrics: TaskMetrics, timestamp: str):
        """Append entry to project report"""
        report_file = self.projects_dir / f"{project_id}.md"

        # Ensure header exists
        if not report_file.exists():
            header = f"# Project Report: {project_id}\n\n"
            header += f"Created: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
            header += "## Tasks\n\n"
            header += "## Summary\n\n"
            report_file.write_text(header)

        # Format and append entry
        status_emoji = "✓" if task_metrics.status == "completed" else "✗"
        entry = self._format_task_entry(task_metrics, status_emoji, timestamp)

        try:
            content = report_file.read_text()
            # Find summary section and insert before it
            summary_idx = content.find("\n## Summary")
            if summary_idx != -1:
                new_content = content[:summary_idx] + f"\n{entry}" + content[summary_idx:]
            else:
                new_content = content + f"\n{entry}"

            report_file.write_text(new_content)
        except Exception as e:
            logger.error(f"Failed to append to project report: {e}")

    def _format_task_entry(self, task_metrics: TaskMetrics, status_emoji: str, timestamp: str) -> str:
        """Format task entry for markdown"""
        time_str = datetime.fromisoformat(timestamp).strftime("%H:%M:%S")

        priority_icon = "🔴" if task_metrics.priority == "serious" else "🟡"

        entry = f"- {status_emoji} [{time_str}] Task #{task_metrics.task_id}: {task_metrics.description[:80]} {priority_icon}\n"
        entry += f"  - Duration: {task_metrics.duration_seconds}s\n"
        entry += f"  - Files modified: {task_metrics.files_modified}, Commands: {task_metrics.commands_executed}\n"

        if task_metrics.git_info:
            entry += f"  - Git: {task_metrics.git_info}\n"

        if task_metrics.error_message:
            entry += f"  - Error: {task_metrics.error_message}\n"

        return entry

    def summarize_daily_report(self, date: Optional[str] = None):
        """Generate end-of-day summary for daily report

        Args:
            date: Report date in YYYY-MM-DD format (default: today)
        """
        if not date:
            date = datetime.utcnow().strftime("%Y-%m-%d")

        report_file = self.daily_dir / f"{date}.md"
        if not report_file.exists():
            logger.warning(f"Report not found: {report_file}")
            return

        try:
            # Parse report to extract metrics
            content = report_file.read_text()
            summary = self._extract_summary_stats(content)

            # Update summary section
            summary_text = self._format_summary(summary, date)

            # Replace or add summary section
            summary_idx = content.find("## Summary")
            if summary_idx != -1:
                next_section = content.find("\n##", summary_idx + 1)
                if next_section != -1:
                    new_content = content[:summary_idx] + summary_text + content[next_section:]
                else:
                    new_content = content[:summary_idx] + summary_text
            else:
                new_content = content + "\n" + summary_text

            report_file.write_text(new_content)
            logger.info(f"Summarized daily report: {date}")

        except Exception as e:
            logger.error(f"Failed to summarize report: {e}")

    def summarize_project_report(self, project_id: str):
        """Generate end-of-day summary for project report

        Args:
            project_id: Project ID
        """
        report_file = self.projects_dir / f"{project_id}.md"
        if not report_file.exists():
            logger.warning(f"Project report not found: {report_file}")
            return

        try:
            content = report_file.read_text()
            summary = self._extract_summary_stats(content)

            # Update summary section
            summary_text = self._format_summary(summary, f"Project: {project_id}")

            # Replace or add summary section
            summary_idx = content.find("## Summary")
            if summary_idx != -1:
                next_section = content.find("\n##", summary_idx + 1)
                if next_section != -1:
                    new_content = content[:summary_idx] + summary_text + content[next_section:]
                else:
                    new_content = content[:summary_idx] + summary_text
            else:
                new_content = content + "\n" + summary_text

            report_file.write_text(new_content)
            logger.info(f"Summarized project report: {project_id}")

        except Exception as e:
            logger.error(f"Failed to summarize project report: {e}")

    def _extract_summary_stats(self, content: str) -> Dict:
        """Extract statistics from report content"""
        stats = {
            "total_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "total_duration": 0,
            "total_files_modified": 0,
            "total_commands": 0,
        }

        lines = content.split("\n")
        for line in lines:
            line = line.strip()

            # Count tasks by status
            if line.startswith("- ✓"):
                stats["completed_tasks"] += 1
                stats["total_tasks"] += 1
            elif line.startswith("- ✗"):
                stats["failed_tasks"] += 1
                stats["total_tasks"] += 1

            # Extract duration
            if "Duration:" in line:
                try:
                    duration_str = line.split("Duration:")[1].split("s")[0].strip()
                    stats["total_duration"] += int(duration_str)
                except:
                    pass

            # Extract files modified
            if "Files modified:" in line:
                try:
                    files_str = line.split("Files modified:")[1].split(",")[0].strip()
                    stats["total_files_modified"] += int(files_str)
                except:
                    pass

            # Extract commands
            if "Commands:" in line:
                try:
                    commands_str = line.split("Commands:")[1].strip()
                    stats["total_commands"] += int(commands_str)
                except:
                    pass

        return stats

    def _format_summary(self, stats: Dict, title: str) -> str:
        """Format summary section"""
        summary_text = f"\n## Summary\n\n"
        summary_text += f"**{title}**\n\n"
        summary_text += f"- Total Tasks: {stats['total_tasks']}\n"
        summary_text += f"- Completed: {stats['completed_tasks']} ✓\n"
        summary_text += f"- Failed: {stats['failed_tasks']} ✗\n"
        summary_text += f"- Success Rate: {stats['completed_tasks']/stats['total_tasks']*100:.1f}%" if stats['total_tasks'] > 0 else "- Success Rate: N/A\n"
        summary_text += f"\n- Total Duration: {stats['total_duration']}s\n"
        summary_text += f"- Files Modified: {stats['total_files_modified']}\n"
        summary_text += f"- Commands Executed: {stats['total_commands']}\n"

        return summary_text

    def _ensure_daily_report_header(self, report_file: Path, date: str):
        """Ensure daily report has proper header"""
        if not report_file.exists():
            date_obj = datetime.strptime(date, "%Y-%m-%d")
            formatted_date = date_obj.strftime("%A, %B %d, %Y")

            header = f"# Daily Report - {formatted_date}\n\n"
            header += f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
            header += "## Tasks\n\n"
            header += "## Summary\n\n"
            report_file.write_text(header)

    def get_daily_report(self, date: Optional[str] = None) -> str:
        """Get daily report content

        Args:
            date: Report date in YYYY-MM-DD format (default: today)

        Returns:
            Report content as markdown string
        """
        if not date:
            date = datetime.utcnow().strftime("%Y-%m-%d")

        report_file = self.daily_dir / f"{date}.md"
        if not report_file.exists():
            return f"No report found for {date}"

        return report_file.read_text()

    def get_project_report(self, project_id: str) -> str:
        """Get project report content

        Args:
            project_id: Project ID

        Returns:
            Report content as markdown string
        """
        report_file = self.projects_dir / f"{project_id}.md"
        if not report_file.exists():
            return f"No report found for project {project_id}"

        return report_file.read_text()

    def list_daily_reports(self) -> List[str]:
        """List all available daily reports

        Returns:
            List of report dates in YYYY-MM-DD format, sorted newest first
        """
        reports = sorted([f.stem for f in self.daily_dir.glob("*.md")], reverse=True)
        return reports

    def list_project_reports(self) -> List[str]:
        """List all available project reports

        Returns:
            List of project IDs
        """
        return sorted([f.stem for f in self.projects_dir.glob("*.md")])

    def update_recent_reports(self):
        """Update recent report cache (today, yesterday, this week)"""
        today = datetime.utcnow().strftime("%Y-%m-%d")
        today_report = self.get_daily_report(today)
        (self.recent_dir / "today.md").write_text(today_report)

        # Yesterday
        yesterday = (datetime.utcnow().fromordinal(datetime.utcnow().toordinal() - 1)).strftime("%Y-%m-%d")
        yesterday_report = self.get_daily_report(yesterday)
        (self.recent_dir / "yesterday.md").write_text(yesterday_report)

        logger.debug("Updated recent reports cache")

    def cleanup_old_reports(self, days: int = 30):
        """Clean up reports older than specified days

        Args:
            days: Days to keep (default: 30)
        """
        cutoff = datetime.utcnow().toordinal() - days

        for report_file in self.daily_dir.glob("*.md"):
            try:
                date_str = report_file.stem
                report_date = datetime.strptime(date_str, "%Y-%m-%d").toordinal()

                if report_date < cutoff:
                    report_file.unlink()
                    logger.info(f"Deleted old report: {date_str}")
            except Exception as e:
                logger.error(f"Failed to clean report {report_file}: {e}")
