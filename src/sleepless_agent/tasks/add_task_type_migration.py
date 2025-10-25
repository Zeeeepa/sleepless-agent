"""Migration script to add task_type column to existing databases"""

import sqlite3
import sys
from pathlib import Path


def migrate_add_task_type(db_path: str) -> None:
    """Add task_type column to tasks table if it doesn't exist"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if column already exists
    cursor.execute("PRAGMA table_info(tasks)")
    columns = [row[1] for row in cursor.fetchall()]

    if 'task_type' in columns:
        print(f"Column 'task_type' already exists in {db_path}")
        conn.close()
        return

    print(f"Adding 'task_type' column to tasks table in {db_path}...")

    # Add the column with default value 'new'
    cursor.execute("""
        ALTER TABLE tasks
        ADD COLUMN task_type TEXT DEFAULT 'new'
    """)

    # Update all existing tasks to have task_type='new' for backwards compatibility
    cursor.execute("""
        UPDATE tasks
        SET task_type = 'new'
        WHERE task_type IS NULL
    """)

    conn.commit()
    conn.close()

    print(f"Successfully added 'task_type' column to {db_path}")


def main():
    """Run migration on specified database or default location"""
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    else:
        # Default database location
        db_path = Path.home() / ".sleepless-agent" / "sleepless.db"

    if not Path(db_path).exists():
        print(f"Database not found at {db_path}")
        sys.exit(1)

    migrate_add_task_type(str(db_path))


if __name__ == "__main__":
    main()
