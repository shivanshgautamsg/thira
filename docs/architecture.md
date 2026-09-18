# THIRA Master Architecture — Production-Grade Technical Specification

> **THIRA is an agentic intelligence platform that continuously perceives a user's digital environment, builds contextual understanding, decides what matters, plans actions, delegates execution to specialized agents and tools, verifies outcomes, and learns from experience.**

---

## Table of Contents

1. [Technology Stack](#1-technology-stack)
2. [Repository Structure](#2-repository-structure)
3. [Component Boundaries & APIs](#3-component-boundaries--apis)
4. [Event Schema Specification](#4-event-schema-specification)
5. [Database Schemas](#5-database-schemas)
6. [MCP Contracts](#6-mcp-contracts)
7. [Agent Lifecycle](#7-agent-lifecycle)
8. [Security Model](#8-security-model)
9. [The THIRA Loop — Runtime Flow](#9-the-thira-loop--runtime-flow)
10. [Observability & Tracing](#10-observability--tracing)
11. [Staged Implementation Plan](#11-staged-implementation-plan)
12. [Open Questions](#12-open-questions)

---

## 1. Technology Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| **Language** | Python 3.12+ | Fastest iteration for LLM integration, richest agent ecosystem |
| **Async runtime** | `asyncio` + `uvloop` | Event-driven architecture demands async-first |
| **API framework** | FastAPI | OpenAPI docs, async-native, dependency injection |
| **Task queue** | Celery + Redis (or `arq` for lightweight) | Long-running agent tasks, plan execution |
| **Event bus** | Redis Streams (V1) → Kafka (V2+) | Lightweight event streaming, upgradeable |
| **Primary DB** | PostgreSQL 16 | Operational data: users, tasks, events, plans, executions |
| **Vector store** | pgvector extension (V1) → Qdrant/Weaviate (V2) | Semantic retrieval for ECHO, unified with Postgres initially |
| **Graph relationships** | PostgreSQL (adjacency + closure tables) (V1) → Neo4j (V2+) | World Model relationships without extra infra |
| **Object storage** | Local filesystem (V1) → S3/MinIO (V2) | Screenshots, PDFs, recordings, artifacts |
| **LLM provider** | OpenAI GPT-4o/4.1 via abstraction layer | Primary provider with `LLMProvider` interface for swap |
| **LLM abstraction** | Custom thin wrapper (not LangChain) | Keep control, avoid framework lock-in, use `litellm` for multi-provider routing |
| **Agent framework** | Custom (inspired by LangGraph state machines) | THIRA loop is opinionated; generic frameworks add friction |
| **MCP runtime** | `mcp` Python SDK | Standard protocol for tool/resource exposure |
| **Containerization** | Docker Compose (V1) → Kubernetes (V3) | Local-first development |
| **Frontend (JARVIS)** | FastAPI + WebSockets (V1) → React/Next.js (V2) | Terminal/chat UI first, rich UI later |
| **Testing** | pytest + pytest-asyncio + testcontainers | Integration tests with real Postgres/Redis in containers |

---

## 2. Repository Structure

```
thira/
├── README.md
├── pyproject.toml                    # Root project config (uv/poetry workspace)
├── docker-compose.yml                # Local dev stack
├── docker-compose.prod.yml
├── Makefile                          # Common commands
├── .env.example
│
├── packages/
│   ├── thira-core/                   # The brain — engines + orchestrator
│   │   ├── pyproject.toml
│   │   └── thira_core/
│   │       ├── __init__.py
│   │       ├── orchestrator.py       # The THIRA loop controller
│   │       ├── perception/
│   │       │   ├── __init__.py
│   │       │   ├── engine.py         # Perception Engine
│   │       │   ├── normalizer.py     # Raw event → ThiraEvent
│   │       │   └── sources/          # Source-specific adapters
│   │       │       ├── gmail.py
│   │       │       ├── calendar.py
│   │       │       └── github.py
│   │       ├── context/
│   │       │   ├── __init__.py
│   │       │   ├── engine.py         # Context Engine
│   │       │   └── enrichment.py     # Entity linking, resolution
│   │       ├── world_model/
│   │       │   ├── __init__.py
│   │       │   ├── model.py          # World Model state
│   │       │   ├── entities.py       # Entity types
│   │       │   └── relationships.py  # Relationship graph
│   │       ├── decision/
│   │       │   ├── __init__.py
│   │       │   ├── engine.py         # Decision Engine
│   │       │   ├── scoring.py        # Multi-factor scoring
│   │       │   └── criteria.py       # Urgency, importance, etc.
│   │       ├── planning/
│   │       │   ├── __init__.py
│   │       │   ├── engine.py         # Planning Engine
│   │       │   ├── planner.py        # Plan generation
│   │       │   └── task_graph.py     # DAG execution model
│   │       ├── policy/
│   │       │   ├── __init__.py
│   │       │   ├── engine.py         # Autonomy & Policy Engine
│   │       │   ├── autonomy.py       # L0-L5 autonomy levels
│   │       │   └── rules.py          # Permission rules
│   │       ├── verification/
│   │       │   ├── __init__.py
│   │       │   ├── engine.py         # Verification Engine
│   │       │   └── strategies.py     # Verification strategies per tool
│   │       ├── failure/
│   │       │   ├── __init__.py
│   │       │   ├── engine.py         # Failure & Recovery Engine
│   │       │   ├── classifier.py     # Failure classification
│   │       │   └── recovery.py       # Recovery strategies
│   │       └── config.py
│   │
│   ├── echo/                         # Experience & Learning Engine
│   │   ├── pyproject.toml
│   │   └── echo/
│   │       ├── __init__.py
│   │       ├── engine.py             # ECHO core
│   │       ├── experience.py         # Experience records
│   │       ├── learning.py           # Pattern extraction
│   │       ├── retrieval.py          # Semantic experience retrieval
│   │       └── store.py              # Storage abstraction
│   │
│   ├── jarvis/                       # Human Interface Layer
│   │   ├── pyproject.toml
│   │   └── jarvis/
│   │       ├── __init__.py
│   │       ├── app.py                # FastAPI app
│   │       ├── chat.py               # Chat interface
│   │       ├── websocket.py          # Real-time communication
│   │       ├── notifications.py      # Proactive notifications
│   │       ├── approval.py           # Human-in-the-loop approval flows
│   │       └── templates/            # Jinja2 templates for V1 web UI
│   │
│   ├── agents/                       # Specialized execution agents
│   │   ├── pyproject.toml
│   │   └── agents/
│   │       ├── __init__.py
│   │       ├── base.py               # BaseAgent interface
│   │       ├── registry.py           # Agent registry
│   │       ├── gmail/
│   │       │   ├── __init__.py
│   │       │   ├── agent.py
│   │       │   └── tools.py          # MCP tools for Gmail
│   │       ├── calendar/
│   │       │   ├── __init__.py
│   │       │   ├── agent.py
│   │       │   └── tools.py
│   │       ├── browser/
│   │       │   ├── __init__.py
│   │       │   ├── agent.py
│   │       │   └── tools.py
│   │       ├── terminal/
│   │       │   ├── __init__.py
│   │       │   ├── agent.py
│   │       │   └── tools.py
│   │       ├── filesystem/
│   │       │   ├── __init__.py
│   │       │   ├── agent.py
│   │       │   └── tools.py
│   │       └── artemis/              # Android execution agent (V2)
│   │           ├── __init__.py
│   │           ├── agent.py
│   │           └── tools.py
│   │
│   ├── shared/                       # Shared types, schemas, utilities
│   │   ├── pyproject.toml
│   │   └── shared/
│   │       ├── __init__.py
│   │       ├── events.py             # ThiraEvent schema
│   │       ├── models.py             # Pydantic domain models
│   │       ├── enums.py              # Autonomy levels, priorities, etc.
│   │       ├── llm/
│   │       │   ├── __init__.py
│   │       │   ├── provider.py       # LLMProvider interface
│   │       │   ├── openai.py         # OpenAI implementation
│   │       │   └── router.py         # Provider routing
│   │       ├── db/
│   │       │   ├── __init__.py
│   │       │   ├── session.py        # Async SQLAlchemy sessions
│   │       │   └── models.py         # ORM models
│   │       ├── bus/
│   │       │   ├── __init__.py
│   │       │   ├── event_bus.py      # Event bus interface
│   │       │   └── redis_bus.py      # Redis Streams implementation
│   │       └── security/
│   │           ├── __init__.py
│   │           ├── auth.py
│   │           └── audit.py          # Action audit trail
│   │
│   └── event-bus/                    # Event ingestion & routing
│       ├── pyproject.toml
│       └── event_bus/
│           ├── __init__.py
│           ├── processor.py          # Event processor
│           ├── router.py             # Event routing
│           └── consumers/            # Source-specific consumers
│               ├── gmail_consumer.py
│               └── webhook_consumer.py
│
├── infra/
│   ├── docker/
│   │   ├── Dockerfile.core
│   │   ├── Dockerfile.jarvis
│   │   └── Dockerfile.worker
│   └── migrations/                   # Alembic migrations
│       ├── alembic.ini
│       └── versions/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
└── docs/
    ├── architecture.md               # This document
    ├── adr/                          # Architecture Decision Records
    └── api/                          # API documentation
```

> [!IMPORTANT]
> **Package management**: Use `uv` with workspace support for the monorepo. Each package under `packages/` has its own `pyproject.toml` with inter-package dependencies declared explicitly.

---

## 3. Component Boundaries & APIs

### 3.1 Orchestrator — The THIRA Loop Controller

The orchestrator is the **central runtime**. It drives the THIRA loop.

```python
# thira_core/orchestrator.py

class ThiraOrchestrator:
    """
    The central THIRA loop controller.
    Drives: PERCEIVE → UNDERSTAND → DECIDE → PLAN → AUTHORIZE → ACT → VERIFY → LEARN
    """

    def __init__(
        self,
        perception: PerceptionEngine,
        context: ContextEngine,
        world_model: WorldModel,
        decision: DecisionEngine,
        planning: PlanningEngine,
        policy: PolicyEngine,
        agent_bus: AgentBus,
        verification: VerificationEngine,
        failure: FailureEngine,
        echo: EchoEngine,
        jarvis: JarvisNotifier,
    ): ...

    async def run_loop(self) -> None:
        """Main event loop — continuously processes events."""
        async for event in self.perception.stream():
            await self.process_event(event)

    async def process_event(self, event: ThiraEvent) -> LoopResult:
        """Single iteration of the THIRA loop."""
        # 1. UNDERSTAND — Enrich with context
        enriched = await self.context.enrich(event, self.world_model)

        # 2. DECIDE — Should we act?
        decision = await self.decision.evaluate(enriched, self.world_model, self.echo)
        if decision.action == DecisionAction.IGNORE:
            return LoopResult(status="ignored")

        # 3. PLAN — How should we act?
        plan = await self.planning.generate(decision, self.world_model)

        # 4. AUTHORIZE — Are we allowed?
        authorized_plan = await self.policy.authorize(plan)
        if authorized_plan.requires_approval:
            await self.jarvis.request_approval(authorized_plan)
            return LoopResult(status="awaiting_approval", plan_id=plan.id)

        # 5. ACT — Execute the plan
        execution = await self.execute_plan(authorized_plan)

        # 6. VERIFY — Did it work?
        verification = await self.verification.verify(execution)

        # 7. LEARN — Record experience
        experience = await self.echo.record(
            context=enriched,
            decision=decision,
            plan=plan,
            execution=execution,
            verification=verification,
        )

        # Update world model
        await self.world_model.apply(execution, verification)

        return LoopResult(status="completed", experience_id=experience.id)

    async def execute_plan(self, plan: AuthorizedPlan) -> Execution:
        """Execute a plan step-by-step via the agent bus."""
        execution = Execution(plan_id=plan.id)
        for step in plan.steps:
            try:
                result = await self.agent_bus.dispatch(step)
                execution.record_step(step, result)
                if not result.success:
                    recovery = await self.failure.handle(step, result)
                    execution.record_recovery(recovery)
                    if recovery.action == RecoveryAction.ABORT:
                        break
            except Exception as e:
                recovery = await self.failure.handle(step, error=e)
                execution.record_recovery(recovery)
                if recovery.action == RecoveryAction.ABORT:
                    break
        return execution
```

---

### 3.2 Engine Interfaces

Each engine has a clear, minimal interface:

```python
# Perception Engine
class PerceptionEngine(Protocol):
    async def stream(self) -> AsyncIterator[ThiraEvent]: ...
    async def ingest(self, raw_event: RawEvent) -> ThiraEvent: ...

# Context Engine
class ContextEngine(Protocol):
    async def enrich(self, event: ThiraEvent, world: WorldModel) -> EnrichedEvent: ...
    async def resolve_entities(self, event: ThiraEvent) -> list[Entity]: ...

# Decision Engine
class DecisionEngine(Protocol):
    async def evaluate(
        self, event: EnrichedEvent, world: WorldModel, echo: EchoEngine
    ) -> Decision: ...

# Planning Engine
class PlanningEngine(Protocol):
    async def generate(self, decision: Decision, world: WorldModel) -> Plan: ...
    async def replan(self, plan: Plan, failure: FailureReport) -> Plan: ...

# Policy Engine
class PolicyEngine(Protocol):
    async def authorize(self, plan: Plan) -> AuthorizedPlan: ...
    async def check_action(self, action: Action) -> PolicyVerdict: ...

# Verification Engine
class VerificationEngine(Protocol):
    async def verify(self, execution: Execution) -> Verification: ...

# Failure Engine
class FailureEngine(Protocol):
    async def handle(
        self, step: PlanStep, result: StepResult | None = None, error: Exception | None = None
    ) -> RecoveryAction: ...

# ECHO Engine
class EchoEngine(Protocol):
    async def record(self, **kwargs) -> Experience: ...
    async def retrieve_similar(self, context: EnrichedEvent, k: int = 5) -> list[Experience]: ...
    async def extract_learnings(self, experience: Experience) -> list[Learning]: ...

# Agent Bus
class AgentBus(Protocol):
    async def dispatch(self, step: PlanStep) -> StepResult: ...
    def register_agent(self, agent: BaseAgent) -> None: ...
    def list_capabilities(self) -> list[Capability]: ...
```

---

### 3.3 Inter-Component Communication

```mermaid
graph LR
    subgraph "THIRA Core Process"
        O[Orchestrator] --> PE[Perception]
        O --> CE[Context]
        O --> WM[World Model]
        O --> DE[Decision]
        O --> PL[Planning]
        O --> PO[Policy]
        O --> VE[Verification]
        O --> FE[Failure]
    end

    subgraph "External"
        EB[Event Bus / Redis Streams] --> PE
        O --> AB[Agent Bus]
        AB --> A1[Gmail Agent]
        AB --> A2[Browser Agent]
        AB --> A3[Terminal Agent]
        O --> ECHO[Echo Engine]
        O --> J[JARVIS / WebSocket]
    end

    style O fill:#4A90D9,color:#fff
    style ECHO fill:#7B68EE,color:#fff
    style J fill:#2ECC71,color:#fff
```

**V1 communication pattern**: All engines are in-process Python objects. The orchestrator calls them directly via async methods. No inter-service RPC in V1.

**Event Bus** (Redis Streams) is used for:
- External event ingestion (Gmail webhooks, calendar push notifications)
- Agent result callbacks
- JARVIS ↔ THIRA real-time messaging (WebSocket bridge)

---

## 4. Event Schema Specification

### 4.1 ThiraEvent — The Universal Event

Every input to THIRA is normalized into this schema:

```python
# shared/events.py

from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4


class EventSource(str, Enum):
    GMAIL = "gmail"
    CALENDAR = "calendar"
    GITHUB = "github"
    SLACK = "slack"
    BROWSER = "browser"
    TERMINAL = "terminal"
    FILESYSTEM = "filesystem"
    ANDROID = "android"
    USER_COMMAND = "user_command"
    SYSTEM = "system"


class EventType(str, Enum):
    MESSAGE_RECEIVED = "message_received"
    MESSAGE_SENT = "message_sent"
    CALENDAR_EVENT_CREATED = "calendar_event_created"
    CALENDAR_EVENT_UPCOMING = "calendar_event_upcoming"
    TASK_CREATED = "task_created"
    TASK_COMPLETED = "task_completed"
    FILE_CHANGED = "file_changed"
    NOTIFICATION = "notification"
    USER_REQUEST = "user_request"
    SYSTEM_ALERT = "system_alert"
    PR_OPENED = "pr_opened"
    PR_MERGED = "pr_merged"
    ISSUE_CREATED = "issue_created"


class EventPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Entity(BaseModel):
    """An entity extracted from an event."""
    name: str
    type: str  # "person", "project", "deadline", "document", etc.
    confidence: float = Field(ge=0.0, le=1.0)
    metadata: dict = Field(default_factory=dict)


class ThiraEvent(BaseModel):
    """The universal event schema — all inputs normalize to this."""
    id: UUID = Field(default_factory=uuid4)
    source: EventSource
    type: EventType
    timestamp: datetime
    actor: str | None = None              # Who/what triggered this
    content: str                           # Human-readable content
    raw_data: dict = Field(default_factory=dict)  # Original payload
    entities: list[Entity] = Field(default_factory=list)
    related_events: list[UUID] = Field(default_factory=list)
    priority: EventPriority = EventPriority.MEDIUM
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: dict = Field(default_factory=dict)

    class Config:
        json_schema_extra = {
            "example": {
                "id": "evt_550e8400-e29b-41d4-a716-446655440000",
                "source": "gmail",
                "type": "message_received",
                "timestamp": "2026-09-18T10:30:00Z",
                "actor": "client@example.com",
                "content": "Please send the revised proposal by 5 PM.",
                "entities": [
                    {"name": "Proposal", "type": "document", "confidence": 0.95},
                    {"name": "5 PM deadline", "type": "deadline", "confidence": 0.92}
                ],
                "priority": "high",
                "confidence": 0.94
            }
        }
```

### 4.2 EnrichedEvent — After Context Engine

```python
class EnrichedEvent(BaseModel):
    """Event after context enrichment."""
    event: ThiraEvent
    resolved_entities: list[ResolvedEntity]   # Linked to World Model
    related_context: list[ContextItem]        # Calendar, recent emails, etc.
    world_model_snapshot: WorldSnapshot        # Relevant slice of world state
    echo_matches: list[ExperienceSummary]      # Similar past experiences
    suggested_priority: EventPriority
    interpretation: str                        # LLM-generated interpretation
```

### 4.3 Redis Streams Event Envelope

```json
{
  "stream": "thira:events",
  "fields": {
    "event_id": "evt_550e8400...",
    "source": "gmail",
    "type": "message_received",
    "payload": "<JSON-serialized ThiraEvent>",
    "ingested_at": "2026-09-18T10:30:01Z"
  }
}
```

---

## 5. Database Schemas

### 5.1 PostgreSQL — Operational Database

```sql
-- ============================================================
-- CORE TABLES
-- ============================================================

CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT UNIQUE NOT NULL,
    name            TEXT NOT NULL,
    preferences     JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- EVENTS
-- ============================================================

CREATE TABLE events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source          TEXT NOT NULL,          -- EventSource enum value
    type            TEXT NOT NULL,          -- EventType enum value
    actor           TEXT,
    content         TEXT NOT NULL,
    raw_data        JSONB DEFAULT '{}',
    entities        JSONB DEFAULT '[]',
    priority        TEXT DEFAULT 'medium',
    confidence      FLOAT DEFAULT 1.0,
    timestamp       TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    metadata        JSONB DEFAULT '{}'
);

CREATE INDEX idx_events_source ON events(source);
CREATE INDEX idx_events_type ON events(type);
CREATE INDEX idx_events_timestamp ON events(timestamp DESC);
CREATE INDEX idx_events_priority ON events(priority);

-- ============================================================
-- WORLD MODEL — Entities & Relationships
-- ============================================================

CREATE TABLE world_entities (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id),
    name            TEXT NOT NULL,
    type            TEXT NOT NULL,          -- person, project, goal, document, etc.
    state           JSONB DEFAULT '{}',     -- Current state attributes
    last_seen       TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_world_entities_type ON world_entities(type);
CREATE INDEX idx_world_entities_user ON world_entities(user_id);

CREATE TABLE world_relationships (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_entity   UUID REFERENCES world_entities(id) ON DELETE CASCADE,
    target_entity   UUID REFERENCES world_entities(id) ON DELETE CASCADE,
    relationship    TEXT NOT NULL,          -- "works_on", "owns", "blocked_by", etc.
    weight          FLOAT DEFAULT 1.0,
    metadata        JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(source_entity, target_entity, relationship)
);

CREATE INDEX idx_relationships_source ON world_relationships(source_entity);
CREATE INDEX idx_relationships_target ON world_relationships(target_entity);

-- ============================================================
-- DECISIONS
-- ============================================================

CREATE TABLE decisions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id        UUID REFERENCES events(id),
    action          TEXT NOT NULL,          -- "act", "ignore", "defer", "escalate"
    urgency         FLOAT,
    importance      FLOAT,
    opportunity     FLOAT,
    effort          FLOAT,
    confidence      FLOAT,
    risk            FLOAT,
    reversibility   FLOAT,
    reasoning       TEXT,                  -- LLM explanation
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- PLANS & EXECUTION
-- ============================================================

CREATE TABLE plans (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_id     UUID REFERENCES decisions(id),
    goal            TEXT NOT NULL,
    status          TEXT DEFAULT 'pending',  -- pending, approved, executing, completed, failed
    steps           JSONB NOT NULL,          -- Ordered list of PlanStep objects
    requires_approval BOOLEAN DEFAULT FALSE,
    approved_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE executions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id         UUID REFERENCES plans(id),
    status          TEXT DEFAULT 'running',  -- running, completed, failed, aborted
    steps_completed INT DEFAULT 0,
    steps_total     INT NOT NULL,
    results         JSONB DEFAULT '[]',      -- Per-step results
    started_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    error           TEXT
);

CREATE TABLE execution_steps (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id    UUID REFERENCES executions(id) ON DELETE CASCADE,
    step_index      INT NOT NULL,
    agent           TEXT NOT NULL,           -- Which agent handled this
    tool            TEXT NOT NULL,           -- Which tool was called
    arguments       JSONB DEFAULT '{}',
    result          JSONB DEFAULT '{}',
    status          TEXT DEFAULT 'pending',  -- pending, running, completed, failed
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    duration_ms     INT,
    error           TEXT
);

-- ============================================================
-- POLICY & PERMISSIONS
-- ============================================================

CREATE TABLE autonomy_policies (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id),
    agent           TEXT NOT NULL,           -- "gmail", "browser", "terminal", "*"
    tool            TEXT NOT NULL,           -- "send_email", "execute_command", "*"
    autonomy_level  INT NOT NULL CHECK (autonomy_level BETWEEN 0 AND 5),
    conditions      JSONB DEFAULT '{}',     -- Additional conditions
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE audit_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id),
    action          TEXT NOT NULL,
    agent           TEXT,
    tool            TEXT,
    arguments       JSONB DEFAULT '{}',
    result_summary  TEXT,
    policy_verdict  TEXT,                   -- "allowed", "approved", "blocked"
    approval_id     UUID,
    timestamp       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_log_user ON audit_log(user_id);
CREATE INDEX idx_audit_log_timestamp ON audit_log(timestamp DESC);

-- ============================================================
-- ECHO — Experience Store
-- ============================================================

CREATE TABLE experiences (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES users(id),
    event_id        UUID REFERENCES events(id),
    decision_id     UUID REFERENCES decisions(id),
    plan_id         UUID REFERENCES plans(id),
    execution_id    UUID REFERENCES executions(id),

    -- The experience record
    context_summary TEXT NOT NULL,
    decision_summary TEXT NOT NULL,
    action_summary  TEXT NOT NULL,
    outcome_summary TEXT NOT NULL,
    success         BOOLEAN,

    -- Learnings extracted
    learnings       JSONB DEFAULT '[]',

    -- Vector embedding for semantic retrieval
    embedding       vector(1536),           -- pgvector, OpenAI embedding dimension

    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_experiences_user ON experiences(user_id);
CREATE INDEX idx_experiences_embedding ON experiences
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ============================================================
-- VERIFICATION
-- ============================================================

CREATE TABLE verifications (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id    UUID REFERENCES executions(id),
    strategy        TEXT NOT NULL,           -- "api_response", "screenshot", "state_check"
    expected        JSONB,
    actual          JSONB,
    passed          BOOLEAN NOT NULL,
    evidence_path   TEXT,                   -- Path to screenshot/log
    details         TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
```

### 5.2 pgvector Setup

```sql
CREATE EXTENSION IF NOT EXISTS vector;
-- The experiences table above uses `vector(1536)` for OpenAI embeddings
-- Use cosine similarity for retrieval:
-- SELECT * FROM experiences
-- ORDER BY embedding <=> $query_embedding
-- LIMIT 5;
```

---

## 6. MCP Contracts

### 6.1 MCP Architecture

Each agent exposes its capabilities via MCP (Model Context Protocol). THIRA acts as an MCP **client** that discovers and calls tools across agents.

```mermaid
graph TB
    subgraph "THIRA Core (MCP Client)"
        TR[Tool Router]
    end

    subgraph "MCP Servers (Agents)"
        G[Gmail MCP Server]
        C[Calendar MCP Server]
        B[Browser MCP Server]
        T[Terminal MCP Server]
        F[Filesystem MCP Server]
    end

    TR -->|stdio/SSE| G
    TR -->|stdio/SSE| C
    TR -->|stdio/SSE| B
    TR -->|stdio/SSE| T
    TR -->|stdio/SSE| F
```

### 6.2 Gmail Agent — MCP Tool Contract

```json
{
  "name": "gmail",
  "description": "Gmail integration for reading, drafting, and sending emails",
  "tools": [
    {
      "name": "list_emails",
      "description": "List emails matching a query",
      "inputSchema": {
        "type": "object",
        "properties": {
          "query": { "type": "string", "description": "Gmail search query" },
          "max_results": { "type": "integer", "default": 10 },
          "label": { "type": "string", "default": "INBOX" }
        },
        "required": ["query"]
      }
    },
    {
      "name": "read_email",
      "description": "Read a specific email by ID",
      "inputSchema": {
        "type": "object",
        "properties": {
          "email_id": { "type": "string" }
        },
        "required": ["email_id"]
      }
    },
    {
      "name": "draft_email",
      "description": "Create a draft email",
      "inputSchema": {
        "type": "object",
        "properties": {
          "to": { "type": "array", "items": { "type": "string" } },
          "subject": { "type": "string" },
          "body": { "type": "string" },
          "cc": { "type": "array", "items": { "type": "string" } },
          "attachments": { "type": "array", "items": { "type": "string" } }
        },
        "required": ["to", "subject", "body"]
      }
    },
    {
      "name": "send_email",
      "description": "Send an email (requires authorization)",
      "inputSchema": {
        "type": "object",
        "properties": {
          "draft_id": { "type": "string" },
          "to": { "type": "array", "items": { "type": "string" } },
          "subject": { "type": "string" },
          "body": { "type": "string" }
        }
      },
      "annotations": {
        "autonomy_level": 3,
        "reversible": false,
        "risk": "medium"
      }
    },
    {
      "name": "label_email",
      "description": "Apply a label to an email",
      "inputSchema": {
        "type": "object",
        "properties": {
          "email_id": { "type": "string" },
          "label": { "type": "string" }
        },
        "required": ["email_id", "label"]
      },
      "annotations": {
        "autonomy_level": 4,
        "reversible": true,
        "risk": "low"
      }
    }
  ],
  "resources": [
    {
      "uri": "gmail://inbox/unread",
      "name": "Unread Inbox",
      "description": "Current unread emails in inbox",
      "mimeType": "application/json"
    }
  ]
}
```

### 6.3 Tool Annotations for Policy Engine

Every MCP tool includes annotations that the Policy Engine uses:

```python
class ToolAnnotation(BaseModel):
    """Metadata attached to each MCP tool for policy decisions."""
    autonomy_level: int = Field(ge=0, le=5)  # Minimum autonomy level required
    reversible: bool = True                   # Can the action be undone?
    risk: str = "low"                         # "low", "medium", "high", "critical"
    requires_confirmation: bool = False        # Always ask user?
    side_effects: list[str] = []              # What external state does this change?
    rate_limit: int | None = None             # Max calls per hour
```

### 6.4 BaseAgent Interface

```python
# agents/base.py

from abc import ABC, abstractmethod

class BaseAgent(ABC):
    """Base class for all THIRA execution agents."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @abstractmethod
    def capabilities(self) -> list[Capability]: ...

    @abstractmethod
    async def execute(self, tool: str, arguments: dict) -> AgentResult: ...

    @abstractmethod
    async def health_check(self) -> bool: ...

    def get_tool_annotations(self, tool: str) -> ToolAnnotation: ...
```

---

## 7. Agent Lifecycle

### 7.1 Agent States

```mermaid
stateDiagram-v2
    [*] --> Registered
    Registered --> Initializing : start()
    Initializing --> Ready : init_complete
    Initializing --> Failed : init_error
    Ready --> Executing : dispatch(task)
    Executing --> Ready : task_complete
    Executing --> Recovering : task_error
    Recovering --> Executing : retry
    Recovering --> Failed : max_retries
    Failed --> Initializing : restart()
    Ready --> Stopped : stop()
    Stopped --> [*]
```

### 7.2 Agent Registration & Discovery

```python
class AgentRegistry:
    """Central registry for all available agents."""

    async def register(self, agent: BaseAgent) -> None:
        """Register an agent and discover its MCP tools."""
        await agent.health_check()
        self._agents[agent.name] = agent
        for cap in agent.capabilities():
            self._capability_index[cap.name] = agent.name

    async def discover_tools(self) -> list[ToolDescriptor]:
        """Return all available tools across all agents."""
        tools = []
        for agent in self._agents.values():
            for cap in agent.capabilities():
                tools.append(ToolDescriptor(
                    agent=agent.name,
                    tool=cap.name,
                    description=cap.description,
                    input_schema=cap.input_schema,
                    annotations=cap.annotations,
                ))
        return tools

    async def route(self, tool_name: str) -> BaseAgent:
        """Find the agent responsible for a given tool."""
        agent_name = self._capability_index.get(tool_name)
        if not agent_name:
            raise ToolNotFoundError(tool_name)
        return self._agents[agent_name]
```

### 7.3 Tool Router (Agent Bus)

```python
class AgentBus:
    """Routes plan steps to the correct agent and tool."""

    def __init__(self, registry: AgentRegistry, policy: PolicyEngine):
        self.registry = registry
        self.policy = policy

    async def dispatch(self, step: PlanStep) -> StepResult:
        """Execute a single plan step."""
        # 1. Find agent
        agent = await self.registry.route(step.tool)

        # 2. Policy check
        verdict = await self.policy.check_action(Action(
            agent=agent.name,
            tool=step.tool,
            arguments=step.arguments,
        ))
        if verdict.blocked:
            return StepResult(success=False, error="Policy blocked")

        # 3. Execute
        start = time.monotonic()
        result = await agent.execute(step.tool, step.arguments)
        duration = time.monotonic() - start

        # 4. Audit
        await self.audit(agent, step, result, verdict, duration)

        return result
```

---

## 8. Security Model

### 8.1 Autonomy Levels

| Level | Name | Behavior | Example |
|-------|------|----------|---------|
| **L0** | Observe | Read-only, no external actions | Fetch unread emails |
| **L1** | Recommend | Suggest actions, no execution | "You should reply to this email" |
| **L2** | Prepare | Draft actions, don't send | Create email draft |
| **L3** | Execute with Approval | Execute after explicit user approval | Send email after user confirms |
| **L4** | Execute Autonomously | Execute without asking (reversible actions) | Label/archive email |
| **L5** | Autonomous Multi-Step | Execute complex plans without interruption | Full proposal workflow |

### 8.2 Policy Evaluation Flow

```python
class PolicyEngine:
    async def authorize(self, plan: Plan) -> AuthorizedPlan:
        """Evaluate every step in a plan against autonomy policies."""
        steps_needing_approval = []

        for step in plan.steps:
            verdict = await self.check_action(Action(
                agent=step.agent,
                tool=step.tool,
                arguments=step.arguments,
            ))
            if verdict.requires_approval:
                steps_needing_approval.append(step)

        return AuthorizedPlan(
            plan=plan,
            requires_approval=len(steps_needing_approval) > 0,
            approval_steps=steps_needing_approval,
            auto_approved_steps=[
                s for s in plan.steps if s not in steps_needing_approval
            ],
        )

    async def check_action(self, action: Action) -> PolicyVerdict:
        """Check a single action against policy rules."""
        # 1. Get tool annotations
        annotations = self._get_tool_annotations(action.agent, action.tool)

        # 2. Get user's autonomy policy for this agent+tool
        user_policy = await self._get_user_policy(action.agent, action.tool)

        # 3. Calculate effective autonomy level
        required_level = annotations.autonomy_level
        granted_level = user_policy.autonomy_level

        # 4. Factor in risk, reversibility, confidence
        if annotations.risk == "critical":
            return PolicyVerdict(blocked=True, reason="Critical risk — always blocked")

        if granted_level >= required_level:
            return PolicyVerdict(allowed=True)
        else:
            return PolicyVerdict(requires_approval=True, reason=f"L{required_level} required, L{granted_level} granted")
```

### 8.3 Audit Trail

Every action produces an immutable audit record:

```python
class AuditRecord(BaseModel):
    id: UUID
    user_id: UUID
    timestamp: datetime
    action: str
    agent: str
    tool: str
    arguments: dict
    result_summary: str
    policy_verdict: str        # "allowed", "approved", "blocked"
    approval_id: UUID | None   # If user approval was obtained
    duration_ms: int
    trace_id: str              # Links to observability trace
```

### 8.4 Credential Management

```yaml
# Credentials are NEVER stored in the database or code
# V1: Environment variables / .env file
# V2: HashiCorp Vault / GCP Secret Manager

# .env.example
OPENAI_API_KEY=sk-...
GMAIL_CLIENT_ID=...
GMAIL_CLIENT_SECRET=...
GMAIL_REFRESH_TOKEN=...
GOOGLE_CALENDAR_CREDENTIALS=...
GITHUB_TOKEN=...
DATABASE_URL=postgresql+asyncpg://thira:thira@localhost:5432/thira
REDIS_URL=redis://localhost:6379/0
```

---

## 9. The THIRA Loop — Runtime Flow

### 9.1 Sequence Diagram

```mermaid
sequenceDiagram
    participant W as Digital World
    participant EB as Event Bus
    participant PE as Perception
    participant CE as Context
    participant WM as World Model
    participant DE as Decision
    participant PL as Planning
    participant PO as Policy
    participant J as JARVIS
    participant AB as Agent Bus
    participant AG as Agent
    participant VE as Verification
    participant EC as ECHO

    W->>EB: Raw event (email, webhook, etc.)
    EB->>PE: Stream event
    PE->>PE: Normalize → ThiraEvent
    PE->>CE: Enrich event
    CE->>WM: Query world state
    WM-->>CE: Context snapshot
    CE->>EC: Retrieve similar experiences
    EC-->>CE: Past experiences
    CE-->>DE: EnrichedEvent
    DE->>DE: Multi-factor evaluation
    DE-->>PL: Decision (act/ignore/defer)

    alt Decision = ACT
        PL->>PL: Generate plan (task graph)
        PL->>PO: Authorize plan
        alt Requires Approval
            PO->>J: Request approval
            J->>J: User approves
            J-->>PO: Approved
        end
        PO-->>AB: AuthorizedPlan
        loop For each step
            AB->>AG: Execute tool
            AG->>W: Perform action
            W-->>AG: Result
            AG-->>AB: StepResult
        end
        AB-->>VE: Execution complete
        VE->>VE: Verify outcomes
        VE-->>EC: Record experience
        EC->>EC: Extract learnings
        EC->>WM: Update world model
    end
```

### 9.2 User Command Flow (JARVIS → THIRA)

When the user sends a message through JARVIS:

```python
# jarvis/chat.py

@app.websocket("/ws/chat")
async def chat(websocket: WebSocket):
    await websocket.accept()
    while True:
        message = await websocket.receive_text()

        # Convert user message to ThiraEvent
        event = ThiraEvent(
            source=EventSource.USER_COMMAND,
            type=EventType.USER_REQUEST,
            timestamp=datetime.utcnow(),
            actor="user",
            content=message,
        )

        # Feed into THIRA loop
        result = await orchestrator.process_event(event)

        # Stream responses back
        await websocket.send_json(result.to_response())
```

---

## 10. Observability & Tracing

### 10.1 Trace Structure

Every THIRA loop iteration produces a trace:

```python
class ThiraTrace(BaseModel):
    """Complete trace of a single THIRA loop iteration."""
    trace_id: str
    trigger: ThiraEvent
    context_retrieval: ContextSummary
    decision: Decision
    plan: Plan | None
    policy_verdict: AuthorizedPlan | None
    execution: Execution | None
    verification: Verification | None
    experience: Experience | None
    total_duration_ms: int
    llm_calls: list[LLMCallRecord]
    started_at: datetime
    completed_at: datetime
```

### 10.2 LLM Call Tracking

```python
class LLMCallRecord(BaseModel):
    """Record of every LLM invocation."""
    call_id: str
    trace_id: str
    engine: str               # Which THIRA engine made the call
    model: str                # "gpt-4o", etc.
    prompt_tokens: int
    completion_tokens: int
    duration_ms: int
    purpose: str              # "entity_extraction", "decision_scoring", "plan_generation"
    cost_usd: float
```

### 10.3 Structured Logging

```python
import structlog

logger = structlog.get_logger()

# Every log entry is JSON-structured with trace context
logger.info(
    "thira.decision.evaluated",
    trace_id=trace.trace_id,
    event_id=str(event.id),
    action=decision.action,
    urgency=decision.urgency,
    importance=decision.importance,
    confidence=decision.confidence,
)
```

---

## 11. Staged Implementation Plan

### Phase 0 — Foundation (Days 1–3)

> **Goal**: Repository scaffold, infrastructure, basic running system

- [ ] Initialize monorepo with `uv` workspace
- [ ] Set up `pyproject.toml` for all packages with inter-dependencies
- [ ] Create `docker-compose.yml` (PostgreSQL 16 + pgvector, Redis)
- [ ] Set up Alembic migrations, run initial schema
- [ ] Implement `shared/` package: Pydantic models, enums, event schemas
- [ ] Implement LLM provider abstraction with OpenAI implementation
- [ ] Implement database session management (async SQLAlchemy)
- [ ] Implement Redis Streams event bus (publish/subscribe)
- [ ] Set up `pytest` + `testcontainers` infrastructure
- [ ] Set up `structlog` for structured JSON logging
- [ ] Basic CI with linting (`ruff`) and type checking (`pyright`)

**Deliverable**: `docker compose up` starts Postgres + Redis; test suite connects to both.

---

### Phase 1 — Core Loop MVP (Days 4–8)

> **Goal**: Prove the THIRA loop end-to-end with one source (user commands via chat)

- [ ] Implement `Orchestrator` with the full loop skeleton
- [ ] Implement `PerceptionEngine` — accept user commands as ThiraEvents
- [ ] Implement `ContextEngine` — basic LLM-based entity extraction and interpretation
- [ ] Implement `WorldModel` — CRUD for entities and relationships in Postgres
- [ ] Implement `DecisionEngine` — LLM-based multi-factor scoring
- [ ] Implement `PlanningEngine` — LLM generates step-by-step plans
- [ ] Implement `PolicyEngine` — rule-based autonomy checking against `autonomy_policies` table
- [ ] Implement `VerificationEngine` — basic API-response verification
- [ ] Implement `FailureEngine` — classify + retry transient failures
- [ ] Implement `EchoEngine` — record experiences, pgvector semantic retrieval
- [ ] Implement `BaseAgent` + `AgentRegistry` + `AgentBus`
- [ ] Implement first agent: **Terminal Agent** (execute shell commands)
- [ ] Implement second agent: **Filesystem Agent** (read/write/search files)
- [ ] Wire JARVIS V1: FastAPI + WebSocket chat interface (terminal-style)

**Deliverable**: User sends a message via JARVIS → THIRA processes it through all engines → executes via terminal/filesystem agent → verifies → records to ECHO → responds.

---

### Phase 2 — Gmail + Calendar Integration (Days 9–12)

> **Goal**: THIRA perceives real events from Gmail and Calendar

- [ ] Implement Gmail Agent (MCP tools: list, read, draft, send, label)
- [ ] Implement Gmail event consumer (webhook or polling)
- [ ] Implement Calendar Agent (MCP tools: list events, create, update)
- [ ] Implement Calendar event consumer (upcoming event notifications)
- [ ] Enhance Context Engine: cross-reference emails ↔ calendar ↔ world model
- [ ] Implement proactive notifications via JARVIS WebSocket
- [ ] Add human-in-the-loop approval flow (JARVIS prompts, user approves)
- [ ] Enhance World Model: auto-create entities from emails/calendar (people, projects, deadlines)
- [ ] Write integration tests with mock Gmail/Calendar APIs

**Deliverable**: THIRA detects an incoming email, cross-references with calendar, decides priority, plans response, asks for approval, drafts and sends email via Gmail agent.

---

### Phase 3 — Browser Agent + Polish (Days 13–16)

> **Goal**: Add browser execution, richer ECHO, V1 UI polish

- [ ] Implement Browser Agent (Playwright-based: navigate, click, type, screenshot, extract)
- [ ] Enhance ECHO: learning extraction (LLM summarizes patterns from experiences)
- [ ] Enhance Decision Engine: consult ECHO for similar past decisions
- [ ] Implement trace viewer (simple web UI to inspect THIRA traces)
- [ ] JARVIS UI polish: styled chat, approval cards, status indicators
- [ ] Add observability: LLM cost tracking, per-engine timing
- [ ] Comprehensive test suite: unit + integration
- [ ] Documentation: README, setup guide, architecture overview

**Deliverable**: A functional THIRA V1 that handles Gmail, Calendar, browser tasks, and terminal commands through the full agentic loop with experience learning.

---

### Phase 4 — V2 Foundations (Post-MVP, Weeks 3–6)

> **Goal**: Scale toward the full architecture

- [ ] ARTEMIS integration (Android execution agent)
- [ ] MCP server mode for each agent (stdio transport)
- [ ] Event streaming from multiple sources (GitHub, Slack)
- [ ] Rich World Model with graph queries
- [ ] Failure recovery with alternative planning
- [ ] Autonomy level auto-adjustment based on ECHO learnings
- [ ] ReleaseLM as a domain agent
- [ ] JARVIS React frontend

---

## 12. Open Questions

> [!IMPORTANT]
> **Q1: Gmail/Calendar Authentication**
> Do you have an existing Google Cloud project with OAuth credentials for Gmail and Calendar API access, or should the spec include steps to set this up? This is a prerequisite for Phase 2.

> [!IMPORTANT]
> **Q2: LLM Cost Budget**
> The Context Engine, Decision Engine, Planning Engine, and ECHO all make LLM calls per event. For a busy inbox, this could be 50+ LLM calls/day. Is there a cost ceiling you want to design around? This affects whether we batch events, use cheaper models for low-priority decisions, or implement a tiered model strategy (GPT-4o-mini for perception, GPT-4o for planning).

> [!IMPORTANT]
> **Q3: JARVIS V1 Interface**
> For the 2–4 week MVP, should JARVIS be:
> - **Terminal-style chat** (WebSocket in browser, text-only) — fastest to build
> - **Styled web UI** (React-based, cards, approval buttons) — better demo
> - **CLI tool** (terminal command) — simplest possible

> [!WARNING]
> **Q4: Data Privacy**
> The World Model stores entities extracted from emails, calendar, etc. — including names, projects, deadlines. Should the spec include encryption-at-rest beyond Postgres defaults, or is local-only deployment sufficient security for V1?

> [!NOTE]
> **Q5: ARTEMIS Scope**
> You mentioned ARTEMIS as an Android execution agent. For V2, should it connect to a physical device via ADB, an Android emulator, or a cloud-based device farm? This affects the agent's transport layer.

---

## Summary

This specification defines THIRA as a **9-stage agentic loop** (Perceive → Understand → Decide → Plan → Authorize → Act → Verify → Learn → Perceive) with:

- **8 core engines** with clean Protocol interfaces
- **PostgreSQL + pgvector + Redis** data architecture
- **MCP-based agent bus** with policy-controlled tool routing
- **6-level autonomy model** (L0–L5) with audit trail
- **4-phase implementation plan** targeting a working MVP in ~16 days
- **ECHO** as a causal experience store with semantic retrieval

The next step after your approval is to scaffold the repository and begin Phase 0.
