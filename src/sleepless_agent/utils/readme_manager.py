"""README file management utilities for consistent README operations."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any
from datetime import datetime

from sleepless_agent.monitoring.logging import get_logger

logger = get_logger(__name__)


class ReadmeManager:
    """Manages README file operations with consistent error handling."""

    def __init__(self, workspace: Path):
        """Initialize README manager.

        Args:
            workspace: Workspace directory path
        """
        self.workspace = Path(workspace)
        self.readme_path = self.workspace / "README.md"

    def ensure_exists(
        self,
        template: str,
        *,
        template_vars: Optional[Dict[str, Any]] = None,
    ) -> Path:
        """Ensure README exists with initial content.

        Args:
            template: Template string for README content
            template_vars: Variables to format into the template

        Returns:
            Path to the README file
        """
        if self.readme_path.exists():
            return self.readme_path

        try:
            content = template
            if template_vars:
                content = template.format(**template_vars)

            self.readme_path.write_text(content)
            logger.debug(f"Created README at: {self.readme_path}")
            return self.readme_path

        except Exception as e:
            logger.error(f"Failed to create README: {e}")
            # Create minimal README on error
            try:
                minimal_content = f"# Task Workspace\n\nCreated: {datetime.now().isoformat()}\n"
                self.readme_path.write_text(minimal_content)
            except:
                pass
            return self.readme_path

    def update_section(
        self,
        section_name: str,
        new_content: str,
        *,
        use_regex: bool = False,
        multiline: bool = False,
    ) -> bool:
        """Update a specific section in the README.

        Args:
            section_name: Name of the section to update (e.g., "## Status")
            new_content: New content for the section
            use_regex: Whether section_name is a regex pattern
            multiline: Whether to match content across multiple lines

        Returns:
            True if update was successful, False otherwise
        """
        if not self.readme_path.exists():
            logger.warning(f"README does not exist at: {self.readme_path}")
            return False

        try:
            content = self.readme_path.read_text()

            if use_regex:
                pattern = section_name
            else:
                # Escape special regex characters in section name
                escaped_name = re.escape(section_name)
                if multiline:
                    # Match section and all content until next section or EOF
                    pattern = rf"{escaped_name}.*?(?=^##\s|\Z)"
                else:
                    # Match just the section header line
                    pattern = rf"^{escaped_name}.*$"

            flags = re.MULTILINE
            if multiline:
                flags |= re.DOTALL

            # Check if section exists
            if re.search(pattern, content, flags):
                # Replace existing section
                updated_content = re.sub(pattern, new_content, content, flags=flags)
            else:
                # Append new section
                updated_content = content + "\n\n" + new_content

            self.readme_path.write_text(updated_content)
            logger.debug(f"Updated section '{section_name}' in README")
            return True

        except Exception as e:
            logger.error(f"Failed to update README section '{section_name}': {e}")
            return False

    def extract_section(
        self,
        section_name: str,
        *,
        use_regex: bool = False,
        include_header: bool = True,
    ) -> Optional[str]:
        """Extract content from a specific section.

        Args:
            section_name: Name of the section to extract
            use_regex: Whether section_name is a regex pattern
            include_header: Whether to include the section header in the result

        Returns:
            Section content or None if not found
        """
        if not self.readme_path.exists():
            return None

        try:
            content = self.readme_path.read_text()

            if use_regex:
                pattern = section_name
            else:
                escaped_name = re.escape(section_name)
                # Match section and content until next section or EOF
                pattern = rf"({escaped_name})(.*?)(?=^##\s|\Z)"

            match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
            if match:
                if include_header:
                    return match.group(0).strip()
                else:
                    # Return just the content, not the header
                    if len(match.groups()) > 1:
                        return match.group(2).strip()
                    else:
                        # If pattern doesn't have groups, return everything after first line
                        lines = match.group(0).strip().split('\n')
                        return '\n'.join(lines[1:]) if len(lines) > 1 else ""

            return None

        except Exception as e:
            logger.error(f"Failed to extract README section '{section_name}': {e}")
            return None

    def extract_list_items(
        self,
        section_name: str,
        *,
        item_pattern: str = r"^[-*]\s+(.+)$",
    ) -> List[str]:
        """Extract list items from a section.

        Args:
            section_name: Name of the section containing the list
            item_pattern: Regex pattern for matching list items

        Returns:
            List of extracted items (without bullets)
        """
        section_content = self.extract_section(section_name, include_header=False)
        if not section_content:
            return []

        items = []
        for line in section_content.split('\n'):
            match = re.match(item_pattern, line.strip())
            if match:
                items.append(match.group(1).strip())

        return items

    def append_to_section(
        self,
        section_name: str,
        content_to_append: str,
    ) -> bool:
        """Append content to an existing section.

        Args:
            section_name: Name of the section to append to
            content_to_append: Content to append

        Returns:
            True if successful, False otherwise
        """
        existing_content = self.extract_section(section_name, include_header=True)
        if existing_content is None:
            # Section doesn't exist, create it
            return self.update_section(section_name, f"{section_name}\n{content_to_append}")

        # Append to existing section
        new_content = f"{existing_content}\n{content_to_append}"
        return self.update_section(section_name, new_content, multiline=True)

    def add_timestamp_entry(
        self,
        section_name: str,
        entry: str,
        *,
        timestamp_format: str = "%Y-%m-%d %H:%M:%S",
    ) -> bool:
        """Add a timestamped entry to a section.

        Args:
            section_name: Section to add the entry to
            entry: Entry content
            timestamp_format: Format for the timestamp

        Returns:
            True if successful, False otherwise
        """
        timestamp = datetime.now().strftime(timestamp_format)
        timestamped_entry = f"[{timestamp}] {entry}"
        return self.append_to_section(section_name, timestamped_entry)

    def update_status(self, status: str) -> bool:
        """Update the status section of the README.

        Args:
            status: New status value

        Returns:
            True if successful, False otherwise
        """
        status_content = f"## Status\n\n**Current Status:** {status}"
        return self.update_section("## Status", status_content, multiline=True)

    def get_content(self) -> Optional[str]:
        """Get the full content of the README.

        Returns:
            README content or None if file doesn't exist
        """
        if not self.readme_path.exists():
            return None

        try:
            return self.readme_path.read_text()
        except Exception as e:
            logger.error(f"Failed to read README: {e}")
            return None

    def backup(self, suffix: Optional[str] = None) -> Optional[Path]:
        """Create a backup of the current README.

        Args:
            suffix: Optional suffix for the backup file

        Returns:
            Path to the backup file or None if failed
        """
        if not self.readme_path.exists():
            return None

        try:
            if suffix:
                backup_name = f"README_{suffix}.md.bak"
            else:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_name = f"README_{timestamp}.md.bak"

            backup_path = self.workspace / backup_name
            backup_path.write_text(self.readme_path.read_text())
            logger.debug(f"Created README backup at: {backup_path}")
            return backup_path

        except Exception as e:
            logger.error(f"Failed to create README backup: {e}")
            return None