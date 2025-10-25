"""Structured logging setup for Sleepless Agent.

This module configures a Rich-powered console logger alongside a JSONL file
sink and exposes helpers for creating context-aware structlog loggers.
"""

from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import structlog
try:
    from structlog.contextvars import merge_contextvars
except ModuleNotFoundError:  # pragma: no cover - fallback for older structlog
    def merge_contextvars(
        logger: Any,
        name: str,
        event_dict: Dict[str, Any],
    ) -> Dict[str, Any]:
        return event_dict
from rich.console import Console

__all__ = [
    "configure_logging",
    "get_logger",
    "logger",
]

_CONFIGURED = False
_CONSOLE = Console(soft_wrap=True, stderr=True)
_DEFAULT_LOG_DIR = Path(os.getenv("SLEEPLESS_LOG_DIR", "workspace/.logs"))

_LEVEL_STYLES: Dict[str, str] = {
    "CRITICAL": "bold white on red",
    "ERROR": "red",
    "WARNING": "yellow",
    "SUCCESS": "green",
    "INFO": "white",
    "DEBUG": "cyan",
    "NOTSET": "grey50",
}


class DedupFilter(logging.Filter):
    """Collapse duplicate log lines emitted within a cooldown window."""

    def __init__(self, cooldown_seconds: float = 1.0) -> None:
        super().__init__()
        self.cooldown_seconds = cooldown_seconds
        self._history: Dict[tuple[str, int, str], float] = {}

    def filter(self, record: logging.LogRecord) -> bool:  # pragma: no cover - simple heuristic
        now = time.monotonic()
        event = getattr(record, "event", None) or getattr(record, "msg", "")
        key = (record.name, record.levelno, str(event))
        last = self._history.get(key)
        if last is not None and (now - last) <= self.cooldown_seconds:
            return False
        self._history[key] = now
        return True


class RichConsoleHandler(logging.Handler):
    """Stream handler that delegates rendering to Rich."""

    def __init__(self) -> None:
        super().__init__()
        self.console = _CONSOLE

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - thin wrapper
        try:
            message = self.format(record)
            self.console.print(message, markup=True, highlight=False, overflow="ignore")
        except Exception:  # pragma: no cover - safety net
            self.handleError(record)


class EventDelta:
    """Add time delta since previous log entry for the same logger name."""

    def __init__(self) -> None:
        self._last_seen: Dict[str, float] = {}

    def __call__(
        self,
        logger: Any,
        name: str,
        event_dict: Dict[str, Any],
    ) -> Dict[str, Any]:
        now = time.monotonic()
        last = self._last_seen.get(name, now)
        event_dict["delta_ms"] = int((now - last) * 1000)
        self._last_seen[name] = now
        return event_dict


def _level_markup(level: str) -> str:
    style = _LEVEL_STYLES.get(level, "white")
    return f"[{style}]{level:<7}[/]"


def _format_delta(delta_ms: Optional[int]) -> str:
    if delta_ms is None:
        return "+000ms"
    if delta_ms >= 1000:
        return f"+{delta_ms / 1000:.1f}s"
    return f"+{delta_ms:03d}ms"


def _format_pairs(pairs: Iterable[tuple[str, Any]]) -> str:
    formatted = []
    for key, value in pairs:
        if isinstance(value, (dict, list, tuple)):
            formatted.append(f"{key}={value!r}")
        elif isinstance(value, str) and " " in value:
            formatted.append(f"{key}=\"{value}\"")
        else:
            formatted.append(f"{key}={value}")
    return " ".join(formatted)


def _console_renderer(
    logger: logging.Logger,
    name: str,
    event_dict: Dict[str, Any],
) -> str:
    timestamp = event_dict.pop("timestamp", None)
    level = event_dict.pop("level", "INFO").upper()
    delta_ms = event_dict.pop("delta_ms", None)
    component = event_dict.pop("logger", name)
    event = event_dict.pop("event", "")

    if isinstance(timestamp, datetime):
        ts_text = timestamp.strftime("%H:%M:%S")
    elif isinstance(timestamp, str):
        ts_text = timestamp.split("T")[-1]
        if "." in ts_text:
            ts_text = ts_text.rsplit(".", 1)[0]
    else:
        ts_text = datetime.now().strftime("%H:%M:%S")

    pairs = _format_pairs(sorted(event_dict.items()))

    prefix = " | ".join(
        (
            f"[dim]{ts_text}[/dim]",
            _level_markup(level),
            f"[dim]{component}[/dim]",
            f"[cyan]{_format_delta(delta_ms)}[/cyan]",
        )
    )

    if pairs:
        return f"{prefix} | {event} {pairs}"
    return f"{prefix} | {event}"


def _json_renderer(
    logger: logging.Logger,
    name: str,
    event_dict: Dict[str, Any],
) -> str:
    return structlog.processors.JSONRenderer(sort_keys=False)(logger, name, event_dict)


def _common_processors() -> list[Any]:
    return [
        merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", key="timestamp"),
        EventDelta(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ]


def configure_logging(
    level: Optional[str] = None,
    log_dir: Optional[Path | str] = None,
) -> None:
    """Configure console + file logging once per process."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    resolved_level = (level or os.getenv("SLEEPLESS_LOG_LEVEL", "INFO")).upper()
    directory = Path(log_dir or _DEFAULT_LOG_DIR).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)

    console_handler = RichConsoleHandler()
    console_handler.setLevel(resolved_level)
    console_handler.addFilter(DedupFilter(cooldown_seconds=1.0))
    console_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=_console_renderer,
            foreign_pre_chain=_common_processors(),
        )
    )

    file_name = directory / f"{datetime.now():%Y%m%d}.log"
    file_handler = logging.FileHandler(file_name, encoding="utf-8")
    file_handler.setLevel(resolved_level)
    file_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=_json_renderer,
            foreign_pre_chain=_common_processors(),
        )
    )

    logging.basicConfig(
        level=getattr(logging, resolved_level, logging.INFO),
        handlers=[console_handler, file_handler],
        force=True,
    )

    structlog.configure(
        processors=_common_processors(),
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    _CONFIGURED = True


def get_logger(name: Optional[str] = None, **context: Any) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger bound to the given name and context."""
    configure_logging()
    base = structlog.get_logger(name or "sleepless")
    if context:
        return base.bind(**context)
    return base


# Provide a default logger for modules that import `logger` directly.
logger = get_logger()
