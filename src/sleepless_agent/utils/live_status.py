"""Lightweight tracker for real-time task execution status."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Iterable, List, Optional

from sleepless_agent.monitoring.logging import get_logger
logger = get_logger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _truncate(text: str, max_length: int = 240) -> str:
    if len(text) <= max_length:
        return text
    return text[: max_length - 1] + "…"


@dataclass
class LiveStatusEntry:
    """Represents the live status for a single task."""

    task_id: int
    description: str = ""
    project_name: Optional[str] = None
    phase: str = "initializing"
    prompt_preview: str = ""
    answer_preview: str = ""
    status: str = "running"
    updated_at: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "project_name": self.project_name,
            "phase": self.phase,
            "prompt_preview": self.prompt_preview,
            "answer_preview": self.answer_preview,
            "status": self.status,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "LiveStatusEntry":
        task_id_raw = payload.get("task_id")
        if task_id_raw is None:
            raise ValueError("task_id is required in payload")
        return cls(
            task_id=int(task_id_raw),
            description=str(payload.get("description", "")),
            project_name=payload.get("project_name"),
            phase=str(payload.get("phase", "initializing")),
            prompt_preview=str(payload.get("prompt_preview", "")),
            answer_preview=str(payload.get("answer_preview", "")),
            status=str(payload.get("status", "running")),
            updated_at=str(payload.get("updated_at", _utc_now_iso())),
        )


class LiveStatusTracker:
    """Persist and retrieve live task execution updates."""

    def __init__(self, storage_path: Path | str):
        self.storage_path = Path(storage_path)
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    # Public API -----------------------------------------------------------------
    def update(self, entry: LiveStatusEntry | Dict[str, Any]) -> None:
        """Upsert the status for a task."""
        payload = entry.to_dict() if isinstance(entry, LiveStatusEntry) else dict(entry)
        task_id = payload.get("task_id")
        if task_id is None:
            raise ValueError("LiveStatusTracker.update requires task_id")

        payload["task_id"] = int(task_id)
        payload.setdefault("updated_at", _utc_now_iso())

        payload["description"] = _truncate(payload.get("description", ""))
        payload["prompt_preview"] = _truncate(payload.get("prompt_preview", ""))
        payload["answer_preview"] = _truncate(payload.get("answer_preview", ""))

        with self._lock:
            data = self._read_all()
            data[str(payload["task_id"])] = payload
            self._atomic_write(data)

    def clear(self, task_id: int) -> None:
        """Remove a task from tracking."""
        with self._lock:
            data = self._read_all()
            if str(task_id) in data:
                del data[str(task_id)]
                self._atomic_write(data)

    def clear_all(self) -> None:
        """Remove all tracked entries."""
        with self._lock:
            if self.storage_path.exists():
                try:
                    self.storage_path.unlink()
                except OSError as exc:
                    logger.debug(f"Failed to remove live status file: {exc}")

    def prune_older_than(self, max_age: timedelta) -> None:
        """Drop entries older than the provided age."""
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - max_age
        with self._lock:
            data = self._read_all()
            changed = False
            for key, value in list(data.items()):
                updated_at = value.get("updated_at")
                stamp: Optional[datetime] = None
                if updated_at is not None:
                    try:
                        stamp = datetime.fromisoformat(str(updated_at))
                    except Exception:
                        stamp = None
                if not stamp or stamp < cutoff:
                    del data[key]
                    changed = True
            if changed:
                self._atomic_write(data)

    def entries(self) -> List[LiveStatusEntry]:
        """Return all entries sorted by most recent update."""
        with self._lock:
            data = self._read_all()

        result = [LiveStatusEntry.from_dict({"task_id": key, **value}) for key, value in data.items()]
        result.sort(key=lambda entry: entry.updated_at, reverse=True)
        return result

    # Internal helpers -----------------------------------------------------------
    def _read_all(self) -> Dict[str, Dict[str, Any]]:
        if not self.storage_path.exists():
            return {}
        try:
            with self.storage_path.open("r", encoding="utf-8") as fh:
                payload = json.load(fh)
                if isinstance(payload, dict):
                    return payload
        except json.JSONDecodeError as exc:
            logger.warning(f"Corrupted live status file {self.storage_path}: {exc}")
        except OSError as exc:
            logger.debug(f"Failed to read live status file {self.storage_path}: {exc}")
        return {}

    def _atomic_write(self, data: Dict[str, Any]) -> None:
        tmp_path = self.storage_path.with_suffix(".tmp")
        try:
            with tmp_path.open("w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            tmp_path.replace(self.storage_path)
        except OSError as exc:
            logger.error(f"Failed to persist live status file {self.storage_path}: {exc}")
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass