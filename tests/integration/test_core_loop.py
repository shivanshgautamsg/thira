"""End-to-end integration test for the full THIRA Core loop."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from agents.filesystem import FilesystemAgent
from agents.registry import AgentBus, AgentRegistry
from echo.engine import EchoEngine
from jarvis.app import ConnectionManager, JarvisNotifier
from thira_core.context.engine import ContextEngine
from thira_core.decision.engine import DecisionEngine
from thira_core.failure.engine import FailureEngine
from thira_core.orchestrator import ThiraOrchestrator
from thira_core.perception.engine import PerceptionEngine
from thira_core.planning.engine import PlanningEngine
from thira_core.policy.engine import PolicyEngine
from thira_core.verification.engine import VerificationEngine
from thira_core.world_model.model import WorldModel


@pytest.mark.asyncio
async def test_full_thira_loop_end_to_end(test_db, in_memory_bus):
    """Test user message -> Full THIRA loop -> Execution -> Verification -> Learning -> Response."""
    with tempfile.TemporaryDirectory() as temp_dir:
        test_file_path = str(Path(temp_dir) / "greeting.txt")

        # Configurable multi-stage mock LLM
        class SequentialMockLLM:
            def __init__(self):
                self.calls = []

            async def complete(self, messages, **kwargs):
                purpose = kwargs.get("purpose", "")
                self.calls.append({"purpose": purpose, "messages": messages})

                if purpose == "context_enrichment":
                    return type(
                        "Resp",
                        (),
                        {
                            "content": json.dumps(
                                {
                                    "entities": [
                                        {"name": "greeting.txt", "type": "file", "confidence": 0.9}
                                    ],
                                    "suggested_priority": "medium",
                                    "interpretation": "User requests creating a greeting text file.",
                                }
                            )
                        },
                    )()
                elif purpose == "decision_scoring":
                    return type(
                        "Resp",
                        (),
                        {
                            "content": json.dumps(
                                {
                                    "action": "act",
                                    "urgency": 0.6,
                                    "importance": 0.7,
                                    "opportunity": 0.5,
                                    "effort": 0.2,
                                    "confidence": 0.95,
                                    "risk": 0.1,
                                    "reversibility": 0.9,
                                    "dependency": 0.0,
                                    "reasoning": "Standard low-risk file creation request from user",
                                }
                            )
                        },
                    )()
                elif purpose == "plan_generation":
                    return type(
                        "Resp",
                        (),
                        {
                            "content": json.dumps(
                                {
                                    "goal": "Write greeting message to file",
                                    "requires_approval": False,
                                    "steps": [
                                        {
                                            "description": "Write greeting to destination path",
                                            "agent": "filesystem",
                                            "tool": "write_file",
                                            "arguments": {
                                                "path": test_file_path,
                                                "content": "Hello THIRA Autonomous Platform!",
                                            },
                                            "depends_on": [],
                                        }
                                    ],
                                }
                            )
                        },
                    )()
                elif purpose == "learning_extraction":
                    return type(
                        "Resp",
                        (),
                        {
                            "content": json.dumps(
                                [
                                    {
                                        "insight": "Direct file writes in user temp directories succeed reliably",
                                        "pattern": "Explicit paths minimize filesystem ambiguity",
                                        "recommendation": "Use absolute paths for deterministic filesystem tasks",
                                        "confidence": 0.9,
                                    }
                                ]
                            )
                        },
                    )()
                return type("Resp", (), {"content": "{}"})()

            async def embed(self, text, **kwargs):
                return [0.05] * 1536

            async def health_check(self):
                return True

        llm = SequentialMockLLM()

        # Instantiate all engines
        perception = PerceptionEngine(event_bus=in_memory_bus)
        context = ContextEngine(llm=llm)
        world_model = WorldModel(db_session_factory=test_db)
        decision = DecisionEngine(llm=llm)
        planning = PlanningEngine(llm=llm)
        policy = PolicyEngine()
        verification = VerificationEngine()
        failure = FailureEngine()
        echo = EchoEngine(db_session_factory=test_db, llm=llm)

        # Agents & Tools
        registry = AgentRegistry()
        fs_agent = FilesystemAgent()
        await registry.register(fs_agent)
        agent_bus = AgentBus(registry=registry)

        # Policy registration
        for cap in fs_agent.capabilities():
            policy.register_tool_annotations("filesystem", cap.name, cap.annotations)

        manager = ConnectionManager()
        jarvis_notifier = JarvisNotifier(connection_manager=manager)

        orchestrator = ThiraOrchestrator(
            perception=perception,
            context=context,
            world_model=world_model,
            decision=decision,
            planning=planning,
            policy=policy,
            agent_bus=agent_bus,
            verification=verification,
            failure=failure,
            echo=echo,
            jarvis=jarvis_notifier,
        )

        # Execute user message through orchestrator
        result = await orchestrator.process_user_message(
            f"Please write 'Hello THIRA Autonomous Platform!' to {test_file_path}"
        )

        # Verify loop execution result
        assert result.status == "completed"
        assert result.trace_id.startswith("trace_")
        assert result.plan_id is not None
        assert result.execution_id is not None
        assert result.experience_id is not None

        # Verify actual file was created on disk
        assert os.path.exists(test_file_path)
        with open(test_file_path) as f:
            content = f.read()
        assert content == "Hello THIRA Autonomous Platform!"

        # Verify ECHO recorded the experience
        similar = await echo.retrieve_similar("Write greeting to file", k=1)
        assert len(similar) == 1
        assert similar[0].id == result.experience_id
        assert similar[0].success is True
        assert len(similar[0].learnings) == 1
        assert "Direct file writes" in similar[0].learnings[0].insight
