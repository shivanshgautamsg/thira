"""Interactive Demo Runner for THIRA Autonomous Platform.

Demonstrates THIRA's 3 killer executive use cases:
1. Morning Executive Briefing (Calendar synthesis + priority tasks)
2. Inbound Client Email Triage & Auto-Drafting (World Model auto-population + policy check)
3. Action Escalation & Human Approval (Safety gating on high-risk actions)

Usage:
    uv run python scripts/demo.py
    uv run python scripts/demo.py --scenario morning_briefing
    uv run python scripts/demo.py --scenario inbound_email
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agents.calendar import CalendarAgent
from agents.filesystem import FilesystemAgent
from agents.gmail import GmailAgent
from agents.registry import AgentBus, AgentRegistry
from agents.terminal import TerminalAgent
from echo.engine import EchoEngine
from event_bus.consumers import GmailEventConsumer
from shared.bus.memory_bus import InMemoryEventBus
from shared.db.models import Base
from shared.enums import AutonomyLevel
from thira_core.context.engine import ContextEngine
from thira_core.decision.engine import DecisionEngine
from thira_core.failure.engine import FailureEngine
from thira_core.orchestrator import ThiraOrchestrator
from thira_core.perception.engine import PerceptionEngine
from thira_core.planning.engine import PlanningEngine
from thira_core.policy.engine import PolicyEngine
from thira_core.verification.engine import VerificationEngine
from thira_core.world_model.model import WorldModel


# ANSI terminal colors
class Colors:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


class DemoLLM:
    """Mock LLM delivering realistic executive scenarios."""

    async def complete(self, messages, **kwargs):
        purpose = kwargs.get("purpose", "")

        if purpose == "entity_extraction":
            return type(
                "Resp",
                (),
                {
                    "content": json.dumps(
                        [
                            {"name": "Alice Smith", "type": "person", "confidence": 0.95},
                            {"name": "Project Artemis", "type": "project", "confidence": 0.92},
                            {
                                "name": "Enterprise Client Corp",
                                "type": "organization",
                                "confidence": 0.88,
                            },
                        ]
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
                            "urgency": 0.85,
                            "importance": 0.90,
                            "opportunity": 0.70,
                            "effort": 0.20,
                            "confidence": 0.95,
                            "risk": 0.10,
                            "reversibility": 0.90,
                            "dependency": 0.0,
                            "reasoning": "Inbound client inquiry regarding project deliverable requires immediate proactive review.",
                        }
                    )
                },
            )()

        elif purpose == "plan_generation":
            prompt_text = " ".join(getattr(m, "content", "") for m in messages).lower()

            if "schedule" in prompt_text or "calendar" in prompt_text or "meeting" in prompt_text:
                plan_payload = {
                    "goal": "Review today's executive schedule and commitments",
                    "requires_approval": False,
                    "steps": [
                        {
                            "description": "Inspect today's upcoming meetings and calendar events",
                            "agent": "calendar",
                            "tool": "list_events",
                            "arguments": {"max_results": 5},
                            "depends_on": [],
                        }
                    ],
                }
            elif "email" in prompt_text or "inbox" in prompt_text or "rfp" in prompt_text or "mail" in prompt_text:
                plan_payload = {
                    "goal": "Triage priority client communications and prepare draft response",
                    "requires_approval": False,
                    "steps": [
                        {
                            "description": "Fetch unread high-priority inbox items",
                            "agent": "gmail",
                            "tool": "list_emails",
                            "arguments": {"query": "is:unread", "max_results": 5},
                            "depends_on": [],
                        },
                        {
                            "description": "Draft client update for Enterprise RFP proposal",
                            "agent": "gmail",
                            "tool": "draft_email",
                            "arguments": {
                                "to": "client@enterprise.com",
                                "subject": "Re: Enterprise Client RFP Review & Confirmation",
                                "body": "Hi Sarah, We have reviewed the RFP requirements and confirmed our delivery timeline. Looking forward to our executive sync tomorrow.",
                            },
                            "depends_on": [],
                        },
                    ],
                }
            elif "governance" in prompt_text or "audit" in prompt_text or "policy" in prompt_text or "security" in prompt_text:
                plan_payload = {
                    "goal": "Audit active workspace agent policies and permissions",
                    "requires_approval": False,
                    "steps": [
                        {
                            "description": "Verify workspace agent permissions and sandbox integrity",
                            "agent": "filesystem",
                            "tool": "list_directory",
                            "arguments": {"path": "."},
                            "depends_on": [],
                        }
                    ],
                }
            else:
                plan_payload = {
                    "goal": "Synthesize comprehensive executive daily operations briefing",
                    "requires_approval": False,
                    "steps": [
                        {
                            "description": "Inspect today's upcoming meetings",
                            "agent": "calendar",
                            "tool": "list_events",
                            "arguments": {"max_results": 5},
                            "depends_on": [],
                        },
                        {
                            "description": "Fetch priority inbox items",
                            "agent": "gmail",
                            "tool": "list_emails",
                            "arguments": {"query": "is:unread", "max_results": 5},
                            "depends_on": [],
                        },
                        {
                            "description": "Draft email reply to Alice Smith with status update",
                            "agent": "gmail",
                            "tool": "draft_email",
                            "arguments": {
                                "to": "alice@enterprise.com",
                                "subject": "Re: Project Artemis Status & Meeting Confirmation",
                                "body": "Hi Alice, We have reviewed the Q3 RFP requirements and are on track for tomorrow. I am preparing the review session agenda.",
                            },
                            "depends_on": [],
                        },
                    ],
                }

            return type("Resp", (), {"content": json.dumps(plan_payload)})()

        elif purpose == "learning_extraction":
            return type(
                "Resp",
                (),
                {
                    "content": json.dumps(
                        [
                            {
                                "pattern": "Executive inbound email triage pattern",
                                "insight": "Autonomous drafting preserves user cognitive load while guaranteeing zero unwanted external sends without confirmation.",
                                "applicability": "High-priority client communications",
                            }
                        ]
                    )
                },
            )()

        return type("Resp", (), {"content": "{}"})()

    async def embed(self, text: str) -> list[float]:
        return [0.05] * 1536


class DemoNotifier:
    """Prints live trace events to the terminal with rich formatting."""

    async def broadcast_trace(self, stage: str, data: dict):
        if stage == "perception":
            print(
                f"\n{Colors.CYAN}  👁️  [PERCEPTION]{Colors.RESET} Ingested event from {Colors.BOLD}{data.get('source')}{Colors.RESET}"
            )
            print(f"     Content: {Colors.DIM}{data.get('content', '')[:100]}...{Colors.RESET}")
        elif stage == "context":
            entities = data.get("entities", [])
            ent_str = ", ".join(f"{e['name']} ({e['type']})" for e in entities)
            print(
                f"  {Colors.BLUE}🧠  [CONTEXT]{Colors.RESET} Auto-resolved World Model Entities: {Colors.BOLD}{ent_str}{Colors.RESET}"
            )
        elif stage == "decision":
            u = int(data.get("urgency", 0) * 100)
            i = int(data.get("importance", 0) * 100)
            r = int(data.get("risk", 0) * 100)
            print(
                f"  {Colors.YELLOW}⚖️   [DECISION]{Colors.RESET} Action: {Colors.BOLD}{data.get('action').upper()}{Colors.RESET} | Urgency: {u}% | Importance: {i}% | Risk: {r}%"
            )
            print(f"     Reasoning: {Colors.DIM}{data.get('reasoning')}{Colors.RESET}")
        elif stage == "plan":
            print(
                f"  {Colors.HEADER}📐  [PLAN]{Colors.RESET} Goal: {Colors.BOLD}{data.get('goal')}{Colors.RESET}"
            )
            for s in data.get("steps", []):
                print(f"     → Step {s['index']}: {s['agent']}.{s['tool']} ({s['description']})")
        elif stage == "step_result":
            status = (
                f"{Colors.GREEN}✓ Done{Colors.RESET}"
                if data.get("success")
                else f"{Colors.RED}✗ Failed{Colors.RESET}"
            )
            print(
                f"  {Colors.GREEN}⚡  [EXECUTION]{Colors.RESET} Step {data.get('step_index')}: {data.get('agent')}.{data.get('tool')} [{status}]"
            )
        elif stage == "echo":
            learnings = data.get("learnings", [])
            print(
                f"  {Colors.CYAN}💡  [ECHO MEMORY]{Colors.RESET} Causal experience committed. Learnings: {Colors.BOLD}{learnings[0] if learnings else 'Indexed into memory'}{Colors.RESET}"
            )

    async def request_approval(self, authorized_plan):
        print(
            f"\n  {Colors.YELLOW}⚠️   [AUTHORIZATION REQUIRED]{Colors.RESET} Plan requires explicit user confirmation:"
        )
        for s in authorized_plan.approval_steps:
            print(f"     • {s.agent}.{s.tool}: {s.description}")

    async def notify(self, message: str, level: str = "info", **kwargs):
        print(f"  🔔 [NOTIFICATION] {message}")


async def build_demo_platform():
    """Build lightweight, in-memory configured THIRA orchestrator for instant demonstration."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    bus = InMemoryEventBus()
    llm = DemoLLM()

    perception = PerceptionEngine(event_bus=bus)
    context = ContextEngine(llm=llm)
    world_model = WorldModel(db_session_factory=session_factory)
    decision = DecisionEngine(llm=llm)
    planning = PlanningEngine(llm=llm)
    policy = PolicyEngine(default_autonomy=AutonomyLevel.L3_EXECUTE_APPROVED)
    verification = VerificationEngine()
    failure = FailureEngine()
    echo = EchoEngine(db_session_factory=session_factory, llm=llm)

    registry = AgentRegistry()
    gmail_agent = GmailAgent()
    calendar_agent = CalendarAgent()
    await registry.register(TerminalAgent())
    await registry.register(FilesystemAgent())
    await registry.register(gmail_agent)
    await registry.register(calendar_agent)

    for cap in gmail_agent.capabilities():
        policy.register_tool_annotations("gmail", cap.name, cap.annotations)
    for cap in calendar_agent.capabilities():
        policy.register_tool_annotations("calendar", cap.name, cap.annotations)

    notifier = DemoNotifier()
    agent_bus = AgentBus(registry=registry)

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
        jarvis=notifier,
    )
    return orchestrator, bus, world_model


async def run_scenario_inbound_email(orchestrator, bus):
    print(f"\n{Colors.BOLD}{'=' * 60}{Colors.RESET}")
    print(
        f"{Colors.BOLD}SCENARIO 1: Proactive Inbound Email Triage & Autonomous Drafting{Colors.RESET}"
    )
    print(f"{Colors.DIM}Client Alice Smith emails with an urgent RFP deadline.{Colors.RESET}")
    print(
        f"{Colors.DIM}THIRA will: Perceive → Link to World Model → Decide to act → Check schedule → Draft reply → Store experience.{Colors.RESET}"
    )
    print(f"{Colors.BOLD}{'=' * 60}{Colors.RESET}")

    consumer = GmailEventConsumer(event_bus=bus)
    raw_email = {
        "id": "msg_demo_001",
        "from": "alice@enterprise.com",
        "subject": "URGENT: Project Artemis Q3 RFP Deadline",
        "body": "Hi, Please confirm our review meeting tomorrow and send over the revised scope document.",
        "labels": ["INBOX", "IMPORTANT"],
    }
    event = await consumer.ingest_message(raw_email)
    result = await orchestrator.process_event(event)

    print(
        f"\n{Colors.GREEN}{Colors.BOLD}▶ Result:{Colors.RESET} Status: {Colors.BOLD}{result.status}{Colors.RESET}"
    )
    print(f"  Trace ID: {result.trace_id}")
    print(f"  Summary: {result.response}\n")


async def main():
    parser = argparse.ArgumentParser(description="THIRA MVP PMF Demo Runner")
    parser.add_argument("--scenario", choices=["inbound_email", "all"], default="all")
    args = parser.parse_args()

    print(
        f"\n{Colors.BOLD}{Colors.HEADER}⚡ THIRA Autonomous Intelligence Platform — Live Demo{Colors.RESET}"
    )
    print(
        f"{Colors.DIM}Initializing platform with in-memory world model and execution bus...{Colors.RESET}"
    )

    orchestrator, bus, world_model = await build_demo_platform()

    if args.scenario in ("inbound_email", "all"):
        await run_scenario_inbound_email(orchestrator, bus)

    print(f"{Colors.BOLD}{'=' * 60}{Colors.RESET}")
    print(f"{Colors.GREEN}{Colors.BOLD}✓ Live Demonstration Completed Successfully!{Colors.RESET}")
    print("To launch the interactive THIRA web application:")
    print(f"  {Colors.CYAN}uv run python main.py{Colors.RESET}")
    print(f"Then open {Colors.BOLD}http://localhost:8000{Colors.RESET} in your browser.")
    print(f"{Colors.BOLD}{'=' * 60}{Colors.RESET}\n")


if __name__ == "__main__":
    asyncio.run(main())
