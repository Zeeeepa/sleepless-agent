"""Tool implementations for Claude to use (file editing, bash execution, etc)"""

import json
import subprocess
from pathlib import Path
from typing import Any, Optional

from loguru import logger


class ToolExecutor:
    """Execute tools on behalf of Claude"""

    def __init__(self, workspace: str, allow_bash: bool = True):
        """Initialize tool executor"""
        self.workspace = Path(workspace)
        self.allow_bash = allow_bash
        self.tools = {
            "read_file": self.read_file,
            "write_file": self.write_file,
            "edit_file": self.edit_file,
            "list_files": self.list_files,
            "bash": self.bash,
            "search_files": self.search_files,
            "get_file_info": self.get_file_info,
        }

    def execute(self, tool_name: str, **kwargs) -> dict:
        """Execute a tool by name"""
        if tool_name not in self.tools:
            return {"error": f"Unknown tool: {tool_name}"}

        try:
            result = self.tools[tool_name](**kwargs)
            return {"success": True, "result": result}
        except Exception as e:
            logger.error(f"Tool execution failed ({tool_name}): {e}")
            return {"success": False, "error": str(e)}

    def read_file(self, path: str) -> str:
        """Read file contents"""
        file_path = self._resolve_path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()

    def write_file(self, path: str, content: str) -> str:
        """Write file contents (creates if doesn't exist)"""
        file_path = self._resolve_path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        return f"File written: {path}"

    def edit_file(self, path: str, old_text: str, new_text: str) -> str:
        """Replace text in file"""
        file_path = self._resolve_path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        if old_text not in content:
            raise ValueError(f"Text not found in {path}")

        new_content = content.replace(old_text, new_text, 1)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        return f"File edited: {path}"

    def list_files(self, path: str = ".", recursive: bool = False, pattern: str = "*") -> list:
        """List files in directory"""
        dir_path = self._resolve_path(path)
        if not dir_path.is_dir():
            raise NotADirectoryError(f"Not a directory: {path}")

        if recursive:
            files = list(dir_path.rglob(pattern))
        else:
            files = list(dir_path.glob(pattern))

        return [str(f.relative_to(self.workspace)) for f in sorted(files)[:50]]

    def bash(self, command: str, timeout: int = 30) -> str:
        """Execute bash command"""
        if not self.allow_bash:
            raise PermissionError("Bash execution is disabled")

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            output = result.stdout
            if result.stderr:
                output += f"\n[STDERR]\n{result.stderr}"

            return output[:5000]  # Limit output

        except subprocess.TimeoutExpired:
            raise TimeoutError(f"Command timed out after {timeout}s: {command}")

    def search_files(self, pattern: str, directory: str = ".") -> list:
        """Search for files matching pattern"""
        dir_path = self._resolve_path(directory)

        results = []
        for file_path in dir_path.rglob("*"):
            if pattern.lower() in file_path.name.lower() and file_path.is_file():
                results.append(str(file_path.relative_to(self.workspace)))

        return results[:30]

    def get_file_info(self, path: str) -> dict:
        """Get file info (size, created, modified)"""
        file_path = self._resolve_path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        stat = file_path.stat()
        return {
            "path": path,
            "size": stat.st_size,
            "created": stat.st_ctime,
            "modified": stat.st_mtime,
            "is_file": file_path.is_file(),
            "is_dir": file_path.is_dir(),
        }

    def _resolve_path(self, path: str) -> Path:
        """Resolve path relative to workspace"""
        if path.startswith("/"):
            path = path[1:]

        resolved = (self.workspace / path).resolve()

        # Security: prevent directory traversal
        if not str(resolved).startswith(str(self.workspace.resolve())):
            raise PermissionError(f"Access denied: {path}")

        return resolved

    def get_tools_schema(self) -> list:
        """Get tool schema for Claude"""
        return [
            {
                "name": "read_file",
                "description": "Read contents of a file",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path relative to workspace"},
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "write_file",
                "description": "Write or create a file",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path relative to workspace"},
                        "content": {"type": "string", "description": "File contents"},
                    },
                    "required": ["path", "content"],
                },
            },
            {
                "name": "edit_file",
                "description": "Replace text in existing file",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path relative to workspace"},
                        "old_text": {"type": "string", "description": "Text to find and replace"},
                        "new_text": {"type": "string", "description": "Replacement text"},
                    },
                    "required": ["path", "old_text", "new_text"],
                },
            },
            {
                "name": "list_files",
                "description": "List files in a directory",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Directory path (default: '.')"},
                        "recursive": {"type": "boolean", "description": "Include subdirectories"},
                        "pattern": {"type": "string", "description": "File pattern to match"},
                    },
                },
            },
            {
                "name": "bash",
                "description": "Execute bash command",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Bash command to execute"},
                        "timeout": {"type": "integer", "description": "Timeout in seconds (max 60)"},
                    },
                    "required": ["command"],
                },
            },
            {
                "name": "search_files",
                "description": "Search for files matching pattern",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "File name pattern to search"},
                        "directory": {"type": "string", "description": "Directory to search (default: '.')"},
                    },
                    "required": ["pattern"],
                },
            },
            {
                "name": "get_file_info",
                "description": "Get file metadata",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path"},
                    },
                    "required": ["path"],
                },
            },
        ]
