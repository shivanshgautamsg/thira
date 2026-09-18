# THIRA — Agentic Intelligence & Autonomous Execution Platform

> THIRA is an agentic intelligence platform that continuously perceives a user's digital environment, builds contextual understanding, decides what matters, plans actions, delegates execution to specialized agents and tools, verifies outcomes, and learns from experience.

## Architecture

```
JARVIS (Human Interface) → THIRA Core (Brain) → Agent Bus (MCP) → Digital World
                                ↕                       ↕
                             ECHO (Memory)        ARTEMIS (Android)
```

## Quick Start

```bash
# Prerequisites: Python 3.12+, Docker, uv

# 1. Clone and install
uv sync

# 2. Start infrastructure
docker compose up -d

# 3. Run database migrations
uv run alembic upgrade head

# 4. Copy and configure environment
cp .env.example .env
# Edit .env with your API keys

# 5. Start THIRA
uv run thira
```

## Project Structure

```
packages/
├── shared/        # Shared types, schemas, LLM abstraction, DB, event bus
├── thira-core/    # The brain — perception, context, decision, planning engines
├── echo/          # Experience & learning engine
├── jarvis/        # Human interface layer (FastAPI + WebSocket)
├── agents/        # Specialized execution agents (Gmail, Browser, Terminal, etc.)
└── event-bus/     # Event ingestion & routing
```

## The THIRA Loop

```
PERCEIVE → UNDERSTAND → DECIDE → PLAN → AUTHORIZE → ACT → VERIFY → LEARN → PERCEIVE
```

## License

Private — All rights reserved.
