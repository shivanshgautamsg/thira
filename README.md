# THIRA — Agentic Intelligence & Autonomous Execution Platform

> **THIRA is an agentic intelligence platform that continuously perceives a user's digital environment, builds contextual understanding, decides what matters, plans actions, delegates execution to specialized agents and tools, verifies outcomes, and learns from experience.**
>
> **JARVIS is the interaction and autonomy experience. ARTEMIS is the device execution capability. ECHO is the experience-memory system.**

---

## The THIRA Loop

```text
                 PERCEIVE
                    ↓
                UNDERSTAND
                    ↓
                  DECIDE
                    ↓
                  PLAN
                    ↓
                AUTHORIZE
                    ↓
                   ACT
                    ↓
                  VERIFY
                    ↓
                  LEARN
                    ↓
                 PERCEIVE ...
```

---

## Architecture Overview

```text
┌─────────────────────────────────────────────────────────────┐
│                    JARVIS (Interface)                       │
│      WebUI / Chat / Proactive Feeds / Approval Modal        │
└──────────────────────────────┬──────────────────────────────┘
                               │ WebSocket / REST
┌──────────────────────────────▼──────────────────────────────┐
│                    THIRA Core (The Brain)                   │
│                                                             │
│   Perception Engine ───────► Context Engine                 │
│         ▲                          │                        │
│         │ (events)                 ▼                        │
│   Event Bus ◄───────        Decision Engine                 │
│         ▲ (in-memory/redis)        │                        │
│         │                          ▼                        │
│   External Events           Planning Engine                 │
│   (Gmail/Cal/FS)                   │                        │
│                                    ▼                        │
│                             Policy Engine                   │
│                        (L0–L5 Autonomy Check)               │
│                                    │                        │
│                                    ▼                        │
│                              Agent Bus                      │
│                                    │                        │
│                                    ▼                        │
│                           Verification Engine               │
│                                    │                        │
│                                    ▼                        │
│                               ECHO Engine ──► World Model   │
│                          (Causal & Vectors)   (Entities/DB) │
└──────────────────────────────┬──────────────────────────────┘
                               │ Tool Invocations (MCP)
┌──────────────────────────────▼──────────────────────────────┐
│                       Execution Agents                      │
│     Filesystem  │  Terminal  │  Browser  │  Gmail  │  Cal   │
└─────────────────────────────────────────────────────────────┘
```

For complete design details, schema specifications, and MCP contracts, see [docs/architecture.md](docs/architecture.md).

---

## Monorepo Structure

```text
thira/
├── main.py                           # Application entry point
├── pyproject.toml                    # uv workspace configuration
├── docker-compose.yml                # PostgreSQL 16 + pgvector, Redis
├── alembic.ini                       # Alembic database migration config
├── .env.example                      # Environment variables template
│
├── packages/
│   ├── shared/                       # Domain models, event schemas, DB manager, LLM abstraction
│   ├── thira-core/                   # Orchestrator + 8 Core Engines
│   ├── echo/                         # Experience & learning engine with semantic vector search
│   ├── jarvis/                       # FastAPI server, WebSocket chat UI, and approval API
│   ├── agents/                       # BaseAgent, AgentRegistry, AgentBus, TerminalAgent, FilesystemAgent
│   └── event-bus/                    # Ingestion processors & event consumers
│
├── infra/                            # Docker & Alembic database migrations
├── tests/                            # Comprehensive unit & integration test suites
└── docs/                             # Architecture specifications & documentation
```

---

## Quick Start

### 1. Prerequisites
- Python 3.12+
- `uv` (recommended package & workspace manager)
- Docker & Docker Compose (optional for local SQLite mode)

### 2. Installation
```bash
# Clone the repository
git clone https://github.com/shivanshgautamsg/thira.git
cd thira

# Install all workspace packages and dependencies
uv sync
```

### 3. Run the Test Suite
```bash
# Run all 30 unit and integration tests
uv run pytest
```

### 4. Running Database Migrations
```bash
# Apply migrations (PostgreSQL + pgvector)
uv run alembic upgrade head
```

### 5. Launch THIRA & JARVIS
```bash
# Configure environment
cp .env.example .env

# Run THIRA
uv run python main.py
```

Open your browser at `http://localhost:8000` to interact with the JARVIS interface.

---

## License

Private — All rights reserved.
