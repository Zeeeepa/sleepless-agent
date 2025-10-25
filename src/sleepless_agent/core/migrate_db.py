#!/usr/bin/env python3
"""Database migration utility for adding indexes to existing databases"""

from typing import List
from sleepless_agent.logging import get_logger
logger = get_logger(__name__)

from sqlalchemy import create_engine, inspect, text


def get_existing_indexes(db_path: str, table_name: str = 'tasks') -> List[str]:
    """Get list of existing index names for a table"""
    engine = create_engine(f"sqlite:///{db_path}", echo=False, future=True)
    inspector = inspect(engine)
    indexes = inspector.get_indexes(table_name)
    return [idx['name'] for idx in indexes]


def migrate_add_indexes(db_path: str) -> dict:
    """Add missing indexes to existing database.

    This function is idempotent - it will only create indexes that don't exist.
    Safe to run multiple times.

    Args:
        db_path: Path to SQLite database file

    Returns:
        Dictionary with migration results:
        {
            'indexes_added': List of index names that were created,
            'indexes_skipped': List of index names that already existed,
            'success': Boolean indicating if migration completed successfully
        }
    """
    engine = create_engine(f"sqlite:///{db_path}", echo=False, future=True)

    # Define indexes to create
    indexes_to_create = [
        ('ix_task_status', 'CREATE INDEX IF NOT EXISTS ix_task_status ON tasks (status)'),
        ('ix_task_project_id', 'CREATE INDEX IF NOT EXISTS ix_task_project_id ON tasks (project_id)'),
        ('ix_task_created_at', 'CREATE INDEX IF NOT EXISTS ix_task_created_at ON tasks (created_at)'),
        ('ix_task_project_status', 'CREATE INDEX IF NOT EXISTS ix_task_project_status ON tasks (project_id, status)'),
        ('ix_task_status_created', 'CREATE INDEX IF NOT EXISTS ix_task_status_created ON tasks (status, created_at)'),
    ]

    # Get existing indexes before migration
    existing_before = set(get_existing_indexes(db_path))

    result = {
        'indexes_added': [],
        'indexes_skipped': [],
        'success': False,
        'error': None,
    }

    try:
        with engine.begin() as conn:
            for idx_name, create_sql in indexes_to_create:
                if idx_name in existing_before:
                    result['indexes_skipped'].append(idx_name)
                    logger.debug(f"Index {idx_name} already exists, skipping")
                else:
                    conn.execute(text(create_sql))
                    result['indexes_added'].append(idx_name)
                    logger.info(f"Created index: {idx_name}")

        # Verify indexes were created
        existing_after = set(get_existing_indexes(db_path))
        expected_indexes = {idx_name for idx_name, _ in indexes_to_create}

        if expected_indexes.issubset(existing_after):
            result['success'] = True
            logger.success(f"Migration complete: {len(result['indexes_added'])} indexes added, "
                          f"{len(result['indexes_skipped'])} already existed")
        else:
            missing = expected_indexes - existing_after
            result['error'] = f"Migration incomplete: Missing indexes {missing}"
            logger.error(result['error'])

    except Exception as e:
        result['error'] = str(e)
        logger.error(f"Migration failed: {e}")

    return result


def main():
    """CLI entry point for database migration"""
    import sys
    from pathlib import Path

    if len(sys.argv) < 2:
        print("Usage: python -m sleepless_agent.core.migrate_db <db_path>")
        print("\nMigrates existing database to add performance indexes.")
        sys.exit(1)

    db_path = sys.argv[1]

    if not Path(db_path).exists():
        print(f"Error: Database file not found: {db_path}")
        sys.exit(1)

    print(f"Migrating database: {db_path}")
    print("=" * 60)

    result = migrate_add_indexes(db_path)

    if result['success']:
        print(f"\n✓ Migration successful!")
        print(f"  - Indexes added: {len(result['indexes_added'])}")
        if result['indexes_added']:
            for idx in result['indexes_added']:
                print(f"    • {idx}")
        print(f"  - Indexes skipped (already exist): {len(result['indexes_skipped'])}")
        if result['indexes_skipped']:
            for idx in result['indexes_skipped']:
                print(f"    • {idx}")
        sys.exit(0)
    else:
        print(f"\n✗ Migration failed!")
        print(f"  Error: {result['error']}")
        sys.exit(1)


if __name__ == '__main__':
    main()
