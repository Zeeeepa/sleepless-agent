"""Analyze codebase for tasks like TODOs, FIXMEs, missing tests, etc."""

import re
from pathlib import Path
from typing import List, Optional, Dict

from loguru import logger


class CodeAnalyzer:
    """Analyze codebase and generate task ideas"""

    # Patterns to search for
    PATTERNS = {
        "todo": r"(?:TODO|FIXME|XXX|HACK)[\s:]*(.+?)(?:\n|$)",
        "pass_statement": r"^\s*pass\s*(?:#|$)",
        "empty_function": r"def\s+\w+\([^)]*\):\s*(?:\"\"\"[^\"]*\"\"\"|''[^']*'')?[^{]*pass\b",
    }

    def __init__(self, workspace_root: Path):
        """Initialize code analyzer"""
        self.workspace_root = Path(workspace_root)

    def find_todos(self) -> List[str]:
        """Find TODO/FIXME comments in codebase"""
        todos = []
        pattern = re.compile(self.PATTERNS["todo"], re.IGNORECASE | re.MULTILINE)

        for py_file in self.workspace_root.rglob("*.py"):
            if self._should_skip_file(py_file):
                continue

            try:
                with open(py_file, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    matches = pattern.findall(content)
                    for match in matches:
                        task = f"Address TODO in {py_file.name}: {match[:100]}"
                        todos.append(task)
            except Exception as e:
                logger.debug(f"Failed to read {py_file}: {e}")

        return todos

    def find_missing_docstrings(self) -> List[str]:
        """Find functions/classes without docstrings"""
        tasks = []
        func_pattern = re.compile(
            r"^(?:def|class)\s+(\w+)\s*\([^)]*\).*?:\s*(?![\"\'])",
            re.MULTILINE,
        )

        for py_file in self.workspace_root.rglob("*.py"):
            if self._should_skip_file(py_file):
                continue

            try:
                with open(py_file, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    # Simple heuristic: find def/class followed by code that doesn't start with docstring
                    lines = content.split("\n")
                    for i, line in enumerate(lines):
                        if (line.strip().startswith("def ") or line.strip().startswith("class ")) and i + 1 < len(
                            lines
                        ):
                            next_line = lines[i + 1].strip()
                            if (
                                next_line
                                and not next_line.startswith('"""')
                                and not next_line.startswith("'''")
                            ):
                                name = line.split("(")[0].split()[-1]
                                task = f"Add docstring to {name} in {py_file.name}"
                                tasks.append(task)
            except Exception as e:
                logger.debug(f"Failed to analyze {py_file}: {e}")

        return tasks[:5]  # Limit to top 5

    def find_unused_imports(self) -> List[str]:
        """Identify potentially unused imports (basic heuristic)"""
        tasks = []

        for py_file in self.workspace_root.rglob("*.py"):
            if self._should_skip_file(py_file):
                continue

            try:
                with open(py_file, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    # Find import lines
                    import_pattern = re.compile(
                        r"^(?:from\s+[\w.]+\s+)?import\s+([\w, ]+)",
                        re.MULTILINE,
                    )
                    imports = import_pattern.findall(content)

                    for import_str in imports:
                        modules = [m.strip().split(" as ")[-1] for m in import_str.split(",")]
                        for module in modules:
                            # Very basic check: count occurrences
                            count = len(re.findall(rf"\b{module}\b", content))
                            if count <= 1:  # Only in import statement
                                task = f"Review unused import '{module}' in {py_file.name}"
                                tasks.append(task)
            except Exception as e:
                logger.debug(f"Failed to check imports in {py_file}: {e}")

        return tasks[:5]  # Limit to top 5

    def find_long_files(self, min_lines: int = 300) -> List[str]:
        """Find files that might need refactoring (too long)"""
        tasks = []

        for py_file in self.workspace_root.rglob("*.py"):
            if self._should_skip_file(py_file):
                continue

            try:
                with open(py_file, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
                    if len(lines) > min_lines:
                        task = f"Refactor {py_file.name} ({len(lines)} lines) - consider breaking into smaller modules"
                        tasks.append(task)
            except Exception as e:
                logger.debug(f"Failed to count lines in {py_file}: {e}")

        return tasks[:3]  # Limit to top 3

    def generate_task_idea(self) -> Optional[str]:
        """Generate a single task idea from code analysis"""
        all_tasks = []

        # Collect from various sources
        all_tasks.extend(self.find_todos())
        all_tasks.extend(self.find_missing_docstrings())
        all_tasks.extend(self.find_unused_imports())
        all_tasks.extend(self.find_long_files())

        if all_tasks:
            import random

            return random.choice(all_tasks)

        return None

    def _should_skip_file(self, file_path: Path) -> bool:
        """Check if file should be skipped"""
        skip_patterns = {".venv", "__pycache__", ".git", ".pytest_cache", "node_modules", ".env"}

        for part in file_path.parts:
            if part in skip_patterns:
                return True

        return False

    def get_analysis_stats(self) -> Dict:
        """Get analysis statistics"""
        return {
            "todos_found": len(self.find_todos()),
            "missing_docstrings": len(self.find_missing_docstrings()),
            "unused_imports": len(self.find_unused_imports()),
            "long_files": len(self.find_long_files()),
        }
