"""Database helper utilities for reducing boilerplate in database operations."""

from __future__ import annotations

from typing import Optional, Type, TypeVar, Any, List
from sqlalchemy.orm import Session, Query
from sqlalchemy.sql.expression import BinaryExpression

from sleepless_agent.storage.sqlite import SQLiteStore
from sleepless_agent.monitoring.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class DatabaseHelper(SQLiteStore):
    """Enhanced database helper with common query patterns."""

    def query_one(
        self,
        model: Type[T],
        *filters: BinaryExpression,
    ) -> Optional[T]:
        """Query for a single record.

        Args:
            model: The SQLAlchemy model class
            *filters: Filter expressions (e.g., Model.id == 1)

        Returns:
            Single record or None
        """
        def _op(session: Session) -> Optional[T]:
            query = session.query(model)
            for f in filters:
                query = query.filter(f)
            return query.first()

        return self._run_read(_op)

    def query_all(
        self,
        model: Type[T],
        *filters: BinaryExpression,
        order_by: Optional[Any] = None,
        limit: Optional[int] = None,
    ) -> List[T]:
        """Query for multiple records.

        Args:
            model: The SQLAlchemy model class
            *filters: Filter expressions
            order_by: Order by clause
            limit: Maximum number of records

        Returns:
            List of records
        """
        def _op(session: Session) -> List[T]:
            query = session.query(model)
            for f in filters:
                query = query.filter(f)
            if order_by is not None:
                query = query.order_by(order_by)
            if limit is not None:
                query = query.limit(limit)
            return query.all()

        return self._run_read(_op)

    def count(
        self,
        model: Type[T],
        *filters: BinaryExpression,
    ) -> int:
        """Count records matching filters.

        Args:
            model: The SQLAlchemy model class
            *filters: Filter expressions

        Returns:
            Number of matching records
        """
        def _op(session: Session) -> int:
            query = session.query(model)
            for f in filters:
                query = query.filter(f)
            return query.count()

        return self._run_read(_op)

    def update_one(
        self,
        model: Type[T],
        record_id: Any,
        **updates: Any,
    ) -> Optional[T]:
        """Update a single record by ID.

        Args:
            model: The SQLAlchemy model class
            record_id: Primary key value
            **updates: Fields to update

        Returns:
            Updated record or None if not found
        """
        def _op(session: Session) -> Optional[T]:
            record = session.query(model).filter(model.id == record_id).first()
            if record:
                for key, value in updates.items():
                    setattr(record, key, value)
                session.flush()
            return record

        return self._run_write(_op)

    def update_where(
        self,
        model: Type[T],
        filters: List[BinaryExpression],
        **updates: Any,
    ) -> int:
        """Update multiple records matching filters.

        Args:
            model: The SQLAlchemy model class
            filters: List of filter expressions
            **updates: Fields to update

        Returns:
            Number of updated records
        """
        def _op(session: Session) -> int:
            query = session.query(model)
            for f in filters:
                query = query.filter(f)
            count = query.update(updates, synchronize_session=False)
            return count

        return self._run_write(_op)

    def create(
        self,
        model: Type[T],
        **fields: Any,
    ) -> T:
        """Create a new record.

        Args:
            model: The SQLAlchemy model class
            **fields: Field values for the new record

        Returns:
            Created record
        """
        def _op(session: Session) -> T:
            record = model(**fields)
            session.add(record)
            session.flush()
            return record

        return self._run_write(_op)

    def delete_one(
        self,
        model: Type[T],
        record_id: Any,
    ) -> bool:
        """Delete a single record by ID.

        Args:
            model: The SQLAlchemy model class
            record_id: Primary key value

        Returns:
            True if record was deleted, False if not found
        """
        def _op(session: Session) -> bool:
            record = session.query(model).filter(model.id == record_id).first()
            if record:
                session.delete(record)
                return True
            return False

        return self._run_write(_op)

    def delete_where(
        self,
        model: Type[T],
        *filters: BinaryExpression,
    ) -> int:
        """Delete records matching filters.

        Args:
            model: The SQLAlchemy model class
            *filters: Filter expressions

        Returns:
            Number of deleted records
        """
        def _op(session: Session) -> int:
            query = session.query(model)
            for f in filters:
                query = query.filter(f)
            count = query.count()
            query.delete(synchronize_session=False)
            return count

        return self._run_write(_op)

    def execute_custom_read(
        self,
        query_builder: Query,
    ) -> Any:
        """Execute a custom read query.

        Args:
            query_builder: SQLAlchemy Query object

        Returns:
            Query result
        """
        def _op(session: Session) -> Any:
            # Bind query to session if needed
            if hasattr(query_builder, 'with_session'):
                query_builder = query_builder.with_session(session)
            return query_builder.all()

        return self._run_read(_op)