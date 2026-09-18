"""Filesystem Agent — Reads, writes, and searches files."""

from __future__ import annotations

import os
from pathlib import Path

import structlog

from agents.base import BaseAgent
from shared.enums import AutonomyLevel, RiskLevel
from shared.models import AgentResult, Capability, ToolAnnotation

logger = structlog.get_logger()


class FilesystemAgent(BaseAgent):
    """Reads, writes, lists, and searches files on the local filesystem."""

    @property
    def name(self) -> str:
        return "filesystem"

    @property
    def description(self) -> str:
        return "Reads, writes, lists, and searches files on the local filesystem"

    def capabilities(self) -> list[Capability]:
        return [
            Capability(
                name="read_file",
                description="Read the contents of a file",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Absolute path to the file"},
                    },
                    "required": ["path"],
                },
                annotations=ToolAnnotation(
                    autonomy_level=AutonomyLevel.L4_EXECUTE_AUTO,
                    reversible=True,
                    risk=RiskLevel.LOW,
                ),
            ),
            Capability(
                name="write_file",
                description="Write content to a file (creates parent directories)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
                annotations=ToolAnnotation(
                    autonomy_level=AutonomyLevel.L3_EXECUTE_APPROVED,
                    reversible=False,
                    risk=RiskLevel.MEDIUM,
                    side_effects=["file_system"],
                ),
            ),
            Capability(
                name="list_directory",
                description="List files and directories at a given path",
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                    },
                    "required": ["path"],
                },
                annotations=ToolAnnotation(
                    autonomy_level=AutonomyLevel.L4_EXECUTE_AUTO,
                    reversible=True,
                    risk=RiskLevel.LOW,
                ),
            ),
        ]

    async def execute(self, tool: str, arguments: dict) -> AgentResult:
        """Execute a filesystem operation."""
        handlers = {
            "read_file": self._read_file,
            "write_file": self._write_file,
            "list_directory": self._list_directory,
        }

        handler = handlers.get(tool)
        if not handler:
            return AgentResult(success=False, error=f"Unknown tool: {tool}")

        return await handler(arguments)

    async def _read_file(self, args: dict) -> AgentResult:
        path = args.get("path", "")
        try:
            content = Path(path).read_text(encoding="utf-8")
            return AgentResult(
                success=True,
                output={"content": content, "path": path, "size": len(content)},
            )
        except FileNotFoundError:
            return AgentResult(success=False, error=f"File not found: {path}")
        except Exception as e:
            return AgentResult(success=False, error=str(e))

    async def _write_file(self, args: dict) -> AgentResult:
        path = args.get("path", "")
        content = args.get("content", "")
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return AgentResult(
                success=True,
                output={"path": path, "bytes_written": len(content)},
            )
        except Exception as e:
            return AgentResult(success=False, error=str(e))

    async def _list_directory(self, args: dict) -> AgentResult:
        path = args.get("path", ".")
        try:
            p = Path(path)
            if not p.is_dir():
                return AgentResult(success=False, error=f"Not a directory: {path}")

            entries = []
            for item in sorted(p.iterdir()):
                entries.append(
                    {
                        "name": item.name,
                        "type": "directory" if item.is_dir() else "file",
                        "size": item.stat().st_size if item.is_file() else None,
                    }
                )

            return AgentResult(
                success=True,
                output={"path": path, "entries": entries, "count": len(entries)},
            )
        except Exception as e:
            return AgentResult(success=False, error=str(e))
