"""System monitoring and health checks"""

import json
import psutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from sleepless_agent.monitoring.logging import get_logger
logger = get_logger(__name__)


class HealthMonitor:
    """Monitor agent health and performance"""

    def __init__(self, db_path: str, results_path: str):
        """Initialize health monitor"""
        self.db_path = Path(db_path)
        self.results_path = Path(results_path)
        self.start_time = datetime.now(timezone.utc).replace(tzinfo=None)
        self.stats = {
            "tasks_completed": 0,
            "tasks_failed": 0,
            "total_processing_time": 0,
            "uptime_seconds": 0,
        }

    def check_health(self) -> dict:
        """Check overall system health"""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        uptime = (now - self.start_time).total_seconds()

        health = {
            "status": "healthy",
            "timestamp": now.isoformat(),
            "uptime_seconds": uptime,
            "uptime_human": self._format_uptime(uptime),
            "system": self._check_system_resources(),
            "database": self._check_database(),
            "storage": self._check_storage(),
        }

        # Determine overall status
        if health["system"]["memory_percent"] > 90 or health["system"]["cpu_percent"] > 80:
            health["status"] = "degraded"

        if not health["database"]["accessible"] or not health["storage"]["accessible"]:
            health["status"] = "unhealthy"

        return health

    def _check_system_resources(self) -> dict:
        """Check CPU and memory usage"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()

            return {
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_available_mb": memory.available / (1024 * 1024),
            }
        except Exception as e:
            logger.error(f"Failed to check system resources: {e}")
            return {"error": str(e)}

    def _check_database(self) -> dict:
        """Check database health"""
        try:
            if not self.db_path.exists():
                return {"accessible": False, "size_mb": 0, "error": "Database file not found"}

            size_mb = self.db_path.stat().st_size / (1024 * 1024)
            modified_ago = (datetime.now(timezone.utc).replace(tzinfo=None) - datetime.fromtimestamp(
                self.db_path.stat().st_mtime
            )).total_seconds()

            return {
                "accessible": True,
                "size_mb": round(size_mb, 2),
                "modified_ago_seconds": int(modified_ago),
            }
        except Exception as e:
            logger.error(f"Failed to check database: {e}")
            return {"accessible": False, "error": str(e)}

    def _check_storage(self) -> dict:
        """Check storage health"""
        try:
            if not self.results_path.exists():
                return {"accessible": False, "count": 0}

            files = list(self.results_path.glob("**/*.json"))
            total_size = sum(f.stat().st_size for f in files) / (1024 * 1024)

            return {
                "accessible": True,
                "count": len(files),
                "total_size_mb": round(total_size, 2),
            }
        except Exception as e:
            logger.error(f"Failed to check storage: {e}")
            return {"accessible": False, "error": str(e)}

    def record_task_completion(self, processing_time: int, success: bool):
        """Record task completion for stats"""
        if success:
            self.stats["tasks_completed"] += 1
            self.stats["total_processing_time"] += processing_time
        else:
            self.stats["tasks_failed"] += 1

    def get_stats(self) -> dict:
        """Get performance statistics"""
        uptime = (datetime.now(timezone.utc).replace(tzinfo=None) - self.start_time).total_seconds()
        self.stats["uptime_seconds"] = int(uptime)

        total_tasks = self.stats["tasks_completed"] + self.stats["tasks_failed"]
        avg_time = (
            self.stats["total_processing_time"] / self.stats["tasks_completed"]
            if self.stats["tasks_completed"] > 0
            else 0
        )

        return {
            **self.stats,
            "total_tasks": total_tasks,
            "success_rate": (
                self.stats["tasks_completed"] / total_tasks * 100 if total_tasks > 0 else 0
            ),
            "avg_processing_time": round(avg_time, 2),
            "uptime_human": self._format_uptime(uptime),
        }

    def _format_uptime(self, seconds: float) -> str:
        """Format uptime in human-readable format"""
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)

        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")

        return " ".join(parts) if parts else "< 1m"

    def log_health_report(self):
        """Log health report"""
        health = self.check_health()
        stats = self.get_stats()

        logger.debug(
            f"Health: {health['status']} | "
            f"Uptime: {health['uptime_human']} | "
            f"Tasks: {stats['tasks_completed']} ✓ {stats['tasks_failed']} ✗ | "
            f"CPU: {health['system'].get('cpu_percent', 'N/A')}% | "
            f"Memory: {health['system'].get('memory_percent', 'N/A')}%"
        )

    def get_uptime(self) -> str:
        """Get formatted uptime"""
        uptime = (datetime.now(timezone.utc).replace(tzinfo=None) - self.start_time).total_seconds()
        return self._format_uptime(uptime)


class PerformanceLogger:
    """Log performance metrics"""

    def __init__(self, log_dir: str = "./workspace/data"):
        """Initialize performance logger"""
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.metrics_file = self.log_dir / "metrics.jsonl"

    def log_task_execution(
        self,
        task_id: int,
        description: str,
        priority: str,
        duration_seconds: int,
        success: bool,
        files_modified: int = 0,
        commands_executed: int = 0,
    ):
        """Log task execution metrics"""
        try:
            metric = {
                "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                "task_id": task_id,
                "description": description[:60],
                "priority": priority,
                "duration_seconds": duration_seconds,
                "success": success,
                "files_modified": files_modified,
                "commands_executed": commands_executed,
            }

            with open(self.metrics_file, "a") as f:
                f.write(json.dumps(metric) + "\n")

        except Exception as e:
            logger.error(f"Failed to log metrics: {e}")

    def get_recent_metrics(self, hours: int = 24) -> list:
        """Get metrics from last N hours"""
        if not self.metrics_file.exists():
            return []

        cutoff_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)
        metrics = []

        try:
            with open(self.metrics_file, "r") as f:
                for line in f:
                    metric = json.loads(line)
                    timestamp = datetime.fromisoformat(metric["timestamp"])
                    if timestamp >= cutoff_time:
                        metrics.append(metric)
        except Exception as e:
            logger.error(f"Failed to read metrics: {e}")

        return metrics

    def get_performance_summary(self, hours: int = 24) -> dict:
        """Get performance summary for last N hours"""
        metrics = self.get_recent_metrics(hours)

        if not metrics:
            return {"count": 0}

        total_duration = sum(m["duration_seconds"] for m in metrics)
        successful = sum(1 for m in metrics if m["success"])
        files_modified = sum(m["files_modified"] for m in metrics)
        commands = sum(m["commands_executed"] for m in metrics)

        return {
            "count": len(metrics),
            "successful": successful,
            "failed": len(metrics) - successful,
            "success_rate": successful / len(metrics) * 100 if metrics else 0,
            "total_duration_seconds": total_duration,
            "avg_duration_seconds": total_duration / len(metrics) if metrics else 0,
            "total_files_modified": files_modified,
            "total_commands_executed": commands,
        }