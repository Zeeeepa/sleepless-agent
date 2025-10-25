"""Shared SQLite utilities for task and result persistence."""

from __future__ import annotations

from typing import Callable, Optional, TypeVar

from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from sleepless_agent.monitoring.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class SQLiteStore:
    """Base helper that encapsulates SQLite engine/session lifecycle."""

    def __init__(self, db_path: str, *, echo: bool = False):
        self.db_path = db_path
        self._echo = echo
        self._create_engine()

    def _create_engine(self) -> None:
        self.engine = create_engine(f"sqlite:///{self.db_path}", echo=self._echo, future=True)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)

    def _reset_engine(self) -> None:
        self.engine.dispose(close=True)
        self._create_engine()

    @staticmethod
    def _should_reset_on_error(exc: OperationalError) -> bool:
        message = str(exc).lower()
        return "readonly" in message or ("sqlite" in message and "locked" in message)

    def _run_write(
        self,
        operation: Callable[[Session], T],
        *,
        retries: int = 2,
    ) -> T:
        last_exc: Optional[Exception] = None
        for attempt in range(retries):
            session = self.SessionLocal()
            try:
                result = operation(session)
                session.commit()
                return result
            except OperationalError as exc:
                session.rollback()
                last_exc = exc
                if self._should_reset_on_error(exc) and attempt < retries - 1:
                    logger.warning(
                        "sqlite.retry",
                        attempt=attempt + 1,
                        retries=retries,
                        error=str(exc),
                    )
                    self._reset_engine()
                    continue
                raise
            except Exception as exc:
                session.rollback()
                last_exc = exc
                raise
            finally:
                session.close()
        if last_exc:
            raise RuntimeError(f"SQLite operation failed after {retries} attempts") from last_exc
        raise RuntimeError("SQLite operation failed without raising an exception")

    def _run_read(self, operation: Callable[[Session], T]) -> T:
        session = self.SessionLocal()
        try:
            return operation(session)
        finally:
            session.close()
