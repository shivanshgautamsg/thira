"""Terminal Agent — Executes shell commands."""

from __future__ import annotations

import asyncio
import os

import structlog

from agents.base import BaseAgent
from shared.enums import AutonomyLevel, RiskLevel
from shared.models import AgentResult, Capability, ToolAnnotation

logger = structlog.get_logger()


class TerminalAgent(BaseAgent):
    """Executes shell commands on the host system.

    This is a powerful but dangerous agent — policy engine controls
    what commands are allowed.
    """

    @property
    def name(self) -> str:
        return "terminal"

    @property
    def description(self) -> str:
        return "Executes shell commands on the host system"

    def capabilities(self) -> list[Capability]:
        return [
            Capability(
                name="execute_command",
                description="Execute a shell command and return stdout/stderr",
                input_schema={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "The command to execute"},
                        "cwd": {"type": "string", "description": "Working directory (optional)"},
                        "timeout": {
                            "type": "integer",
                            "description": "Timeout in seconds",
                            "default": 30,
                        },
                    },
                    "required": ["command"],
                },
                annotations=ToolAnnotation(
                    autonomy_level=AutonomyLevel.L3_EXECUTE_APPROVED,
                    reversible=False,
                    risk=RiskLevel.HIGH,
                    side_effects=["system_state"],
                ),
            ),
        ]

    async def execute(self, tool: str, arguments: dict) -> AgentResult:
        """Execute a shell command."""
        if tool != "execute_command":
            return AgentResult(success=False, error=f"Unknown tool: {tool}")

        command = arguments.get("command", "")
        cwd = arguments.get("cwd")
        timeout = arguments.get("timeout", 30)

        if not command:
            return AgentResult(success=False, error="No command provided")

        logger.info("terminal.executing", command=command[:100], cwd=cwd, timeout=timeout)

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )

            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)

            stdout_str = stdout.decode("utf-8", errors="replace").strip()
            stderr_str = stderr.decode("utf-8", errors="replace").strip()

            success = process.returncode == 0

            return AgentResult(
                success=success,
                output={
                    "stdout": stdout_str,
                    "stderr": stderr_str,
                    "return_code": process.returncode,
                },
                error=stderr_str if not success else None,
            )

        except TimeoutError:
            return AgentResult(
                success=False,
                error=f"Command timed out after {timeout}s",
            )
        except Exception as e:
            return AgentResult(success=False, error=str(e))
