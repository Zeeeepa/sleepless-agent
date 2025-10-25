"""Directory management utility for consistent directory operations."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Union

from sleepless_agent.monitoring.logging import get_logger

logger = get_logger(__name__)


class DirectoryManager:
    """Centralized directory management with consistent error handling."""

    @staticmethod
    def ensure_exists(path: Union[str, Path], *, log_creation: bool = False) -> Path:
        """Ensure a directory exists, creating it if necessary.

        Args:
            path: Directory path (string or Path object)
            log_creation: Whether to log directory creation

        Returns:
            Path object for the directory

        Raises:
            PermissionError: If unable to create directory due to permissions
            OSError: If unable to create directory for other reasons
        """
        dir_path = Path(path) if isinstance(path, str) else path

        try:
            existed = dir_path.exists()
            dir_path.mkdir(parents=True, exist_ok=True)

            if log_creation and not existed:
                logger.debug(f"Created directory: {dir_path}")

            return dir_path

        except PermissionError as exc:
            logger.error(f"Permission denied creating directory: {dir_path}")
            raise
        except OSError as exc:
            logger.error(f"Failed to create directory {dir_path}: {exc}")
            raise

    @staticmethod
    def ensure_multiple(paths: List[Union[str, Path]], *, log_creation: bool = False) -> List[Path]:
        """Ensure multiple directories exist.

        Args:
            paths: List of directory paths
            log_creation: Whether to log directory creation

        Returns:
            List of Path objects for the directories

        Raises:
            PermissionError: If unable to create any directory due to permissions
            OSError: If unable to create any directory for other reasons
        """
        result_paths = []
        for path in paths:
            result_paths.append(
                DirectoryManager.ensure_exists(path, log_creation=log_creation)
            )
        return result_paths

    @staticmethod
    def ensure_parent_exists(file_path: Union[str, Path], *, log_creation: bool = False) -> Path:
        """Ensure the parent directory of a file exists.

        Args:
            file_path: Path to a file
            log_creation: Whether to log directory creation

        Returns:
            Path object for the parent directory

        Raises:
            PermissionError: If unable to create parent directory due to permissions
            OSError: If unable to create parent directory for other reasons
        """
        file_path = Path(file_path) if isinstance(file_path, str) else file_path
        parent_dir = file_path.parent

        return DirectoryManager.ensure_exists(parent_dir, log_creation=log_creation)

    @staticmethod
    def cleanup_empty(path: Union[str, Path]) -> bool:
        """Remove a directory if it's empty.

        Args:
            path: Directory path

        Returns:
            True if directory was removed, False otherwise
        """
        dir_path = Path(path) if isinstance(path, str) else path

        try:
            if dir_path.exists() and dir_path.is_dir():
                # Check if directory is empty
                if not any(dir_path.iterdir()):
                    dir_path.rmdir()
                    logger.debug(f"Removed empty directory: {dir_path}")
                    return True
            return False
        except OSError as exc:
            logger.warning(f"Failed to remove directory {dir_path}: {exc}")
            return False

    @staticmethod
    def safe_create_file(file_path: Union[str, Path], content: str = "",
                        *, overwrite: bool = False) -> Path:
        """Safely create a file, ensuring parent directory exists.

        Args:
            file_path: Path to the file
            content: Initial content for the file
            overwrite: Whether to overwrite existing file

        Returns:
            Path object for the created file

        Raises:
            FileExistsError: If file exists and overwrite is False
            PermissionError: If unable to create file due to permissions
            OSError: If unable to create file for other reasons
        """
        file_path = Path(file_path) if isinstance(file_path, str) else file_path

        # Ensure parent directory exists
        DirectoryManager.ensure_parent_exists(file_path)

        # Check if file exists
        if file_path.exists() and not overwrite:
            raise FileExistsError(f"File already exists: {file_path}")

        try:
            file_path.write_text(content)
            logger.debug(f"Created file: {file_path}")
            return file_path
        except PermissionError:
            logger.error(f"Permission denied creating file: {file_path}")
            raise
        except OSError as exc:
            logger.error(f"Failed to create file {file_path}: {exc}")
            raise

    @staticmethod
    def get_size(path: Union[str, Path], *, human_readable: bool = False) -> Union[int, str]:
        """Get the total size of a directory or file.

        Args:
            path: Path to directory or file
            human_readable: Return size in human-readable format

        Returns:
            Size in bytes (int) or human-readable string
        """
        path = Path(path) if isinstance(path, str) else path

        if not path.exists():
            return "0 B" if human_readable else 0

        total_size = 0

        if path.is_file():
            total_size = path.stat().st_size
        elif path.is_dir():
            for item in path.rglob("*"):
                if item.is_file():
                    total_size += item.stat().st_size

        if human_readable:
            return DirectoryManager._format_size(total_size)
        return total_size

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Format size in bytes to human-readable format.

        Args:
            size_bytes: Size in bytes

        Returns:
            Human-readable size string
        """
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"