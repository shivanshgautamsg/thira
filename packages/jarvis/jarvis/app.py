"""THIRA FastAPI application — the enterprise web server powering the human interface."""

from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import structlog
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from shared.enums import EventSource, EventType
from shared.events import ThiraEvent

logger = structlog.get_logger()

# The orchestrator is injected at startup
_orchestrator = None


def set_orchestrator(orchestrator) -> None:
    """Inject the THIRA orchestrator (called at startup)."""
    global _orchestrator
    _orchestrator = orchestrator


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown."""
    global _orchestrator
    logger.info("thira.starting")
    if _orchestrator is None:
        try:
            from main import create_thira

            _orchestrator = await create_thira()
            logger.info("thira.orchestrator_auto_initialized")
        except Exception as e:
            logger.warning("thira.auto_init_skipped", reason=str(e))
    yield
    logger.info("thira.stopping")


app = FastAPI(
    title="THIRA — Autonomous Intelligence Platform",
    description="The enterprise-grade human interface of the THIRA agentic intelligence platform.",
    version="0.2.0",
    lifespan=lifespan,
)


# ─── WebSocket Chat & Trace Broadcasting ─────────────────────


class ConnectionManager:
    """Manages active WebSocket connections."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("thira.ws_connected", total=len(self.active_connections))

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info("thira.ws_disconnected", total=len(self.active_connections))

    async def broadcast(self, message: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)


manager = ConnectionManager()


@app.websocket("/ws/chat")
async def chat_endpoint(websocket: WebSocket):
    """Main chat WebSocket endpoint.

    User sends messages → THIRA processes through full loop → responses & trace stream back.
    """
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "")

            if not message:
                continue

            logger.info("thira.message_received", message=message[:100])

            event = ThiraEvent(
                source=EventSource.USER_COMMAND,
                type=EventType.USER_REQUEST,
                timestamp=datetime.now(UTC),
                actor="user",
                content=message,
            )

            if _orchestrator:
                await websocket.send_json(
                    {
                        "type": "status",
                        "status": "processing",
                        "message": "Coordinating agents & evaluating request...",
                    }
                )

                result = await _orchestrator.process_event(event)

                await websocket.send_json(
                    {
                        "type": "response",
                        "status": result.status,
                        "message": result.response or f"Completed with status: {result.status}",
                        "trace_id": result.trace_id,
                        "plan_id": str(result.plan_id) if result.plan_id else None,
                    }
                )
            else:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "THIRA orchestrator not initialized.",
                    }
                )

    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ─── Approval Flow & Trace Notifier ──────────────────────────


class JarvisNotifier:
    """Handles notifications, live trace broadcasts, and approval requests from THIRA."""

    def __init__(self, connection_manager: ConnectionManager):
        self._manager = connection_manager
        self._pending_approvals: dict[str, dict] = {}

    async def broadcast_trace(self, stage: str, data: dict) -> None:
        """Broadcast live cognitive trace lifecycle updates to connected clients."""
        await self._manager.broadcast(
            {
                "type": "trace",
                "stage": stage,
                "data": data,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

    async def request_approval(self, authorized_plan) -> None:
        """Send an approval request to the user via WebSocket."""
        plan_id = str(authorized_plan.plan.id)
        approval_steps = [
            {
                "index": s.index,
                "description": s.description,
                "agent": s.agent,
                "tool": s.tool,
            }
            for s in authorized_plan.approval_steps
        ]

        self._pending_approvals[plan_id] = {
            "plan": authorized_plan,
            "requested_at": datetime.now(UTC).isoformat(),
        }

        await self._manager.broadcast(
            {
                "type": "approval_request",
                "plan_id": plan_id,
                "goal": authorized_plan.plan.goal,
                "steps_requiring_approval": approval_steps,
                "message": f"Authorization required for plan: {authorized_plan.plan.goal}",
            }
        )
        logger.info("thira.approval_requested", plan_id=plan_id)

    async def notify(self, message: str, level: str = "info", **kwargs) -> None:
        """Send a notification to the user."""
        await self._manager.broadcast(
            {
                "type": "notification",
                "level": level,
                "message": message,
                "kwargs": kwargs,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )


# ─── REST API & Executive Endpoints ───────────────────────────


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the THIRA executive operations console."""
    return CHAT_HTML


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "thira", "timestamp": datetime.now(UTC).isoformat()}


@app.post("/api/approve/{plan_id}")
async def approve_plan(plan_id: str, approved: bool = True):
    """Approve or reject a pending plan."""
    if _orchestrator:
        result = await _orchestrator.handle_approval(uuid.UUID(plan_id), approved)
        return {"status": result.status, "plan_id": plan_id}
    return {"error": "Orchestrator not initialized"}


@app.post("/api/scenarios/demo/{scenario_name}")
async def trigger_demo_scenario(scenario_name: str):
    """Trigger an executive workflow scenario."""
    if not _orchestrator:
        return {"error": "Orchestrator not initialized"}

    if scenario_name in ("morning_briefing", "executive_briefing"):
        event = ThiraEvent(
            source=EventSource.USER_COMMAND,
            type=EventType.USER_REQUEST,
            timestamp=datetime.now(UTC),
            actor="user",
            content="Generate my executive morning briefing. Review upcoming calendar events and summarize priority items.",
        )
    elif scenario_name in ("inbound_email", "inbound_rfp"):
        event = ThiraEvent(
            source=EventSource.GMAIL,
            type=EventType.MESSAGE_RECEIVED,
            timestamp=datetime.now(UTC),
            actor="client@enterprise.com",
            content="Subject: URGENT: Q3 Proposal Review and Deadline\nFrom: client@enterprise.com\n\nHi, Please confirm the RFP submission and schedule our review meeting tomorrow at 3 PM.",
            raw_data={
                "from": "client@enterprise.com",
                "subject": "URGENT: Q3 Proposal Review and Deadline",
            },
        )
    elif scenario_name in ("schedule_check", "schedule_sync"):
        event = ThiraEvent(
            source=EventSource.CALENDAR,
            type=EventType.CALENDAR_EVENT_UPCOMING,
            timestamp=datetime.now(UTC),
            actor="calendar",
            content="What is on my schedule today? List upcoming executive meetings and commitments.",
        )
    elif scenario_name in ("governance_audit", "security_audit"):
        event = ThiraEvent(
            source=EventSource.USER_COMMAND,
            type=EventType.USER_REQUEST,
            timestamp=datetime.now(UTC),
            actor="user",
            content="Audit active agent security policies, permissions, and sandbox integrity.",
        )
    else:
        return {"error": f"Unknown scenario: {scenario_name}"}

    result = await _orchestrator.process_event(event)
    return {
        "status": result.status,
        "trace_id": result.trace_id,
        "plan_id": str(result.plan_id) if result.plan_id else None,
        "response": result.response,
    }


# ─── Chat UI HTML + Enterprise Governance Console ────────────

CHAT_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>THIRA — Enterprise Autonomous Operations</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Outfit:wght@500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }

        :root {
            --bg-base: #090a0f;
            --bg-surface: #11141f;
            --bg-elevated: #181d2d;
            --bg-subtle: #21273d;
            --border-subtle: rgba(255, 255, 255, 0.08);
            --border-strong: rgba(255, 255, 255, 0.16);
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --text-muted: #64748b;
            --accent: #6366f1;
            --accent-hover: #4f46e5;
            --accent-soft: rgba(99, 102, 241, 0.15);
            --success: #10b981;
            --success-soft: rgba(16, 185, 129, 0.15);
            --warning: #f59e0b;
            --warning-soft: rgba(245, 158, 11, 0.15);
            --danger: #ef4444;
            --danger-soft: rgba(239, 68, 68, 0.15);
            --font-mono: 'JetBrains Mono', monospace;
            --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.25);
            --shadow-md: 0 4px 12px 0 rgba(0, 0, 0, 0.35);
            --shadow-lg: 0 10px 25px -3px rgba(0, 0, 0, 0.5);
        }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg-base);
            color: var(--text-primary);
            height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            -webkit-font-smoothing: antialiased;
        }

        /* Top Enterprise Navigation */
        .top-nav {
            padding: 12px 24px;
            background: var(--bg-surface);
            border-bottom: 1px solid var(--border-subtle);
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-shrink: 0;
            z-index: 20;
        }

        .brand-section {
            display: flex;
            align-items: center;
            gap: 14px;
        }

        .brand-logo {
            width: 36px;
            height: 36px;
            border-radius: 9px;
            background: linear-gradient(135deg, #6366f1, #8b5cf6);
            display: flex;
            align-items: center;
            justify-content: center;
            font-family: 'Outfit', sans-serif;
            font-weight: 700;
            font-size: 18px;
            color: #ffffff;
            box-shadow: 0 0 14px rgba(99, 102, 241, 0.4);
        }

        .brand-text h1 {
            font-family: 'Outfit', sans-serif;
            font-size: 17px;
            font-weight: 700;
            letter-spacing: -0.02em;
            color: #ffffff;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .brand-text p {
            font-size: 11px;
            color: var(--text-secondary);
            font-weight: 500;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }

        .workspace-tag {
            background: var(--bg-elevated);
            border: 1px solid var(--border-subtle);
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 12px;
            color: var(--text-secondary);
            display: flex;
            align-items: center;
            gap: 6px;
            margin-left: 12px;
        }

        /* Top Action Buttons */
        .action-workflows {
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .workflow-btn {
            background: var(--bg-elevated);
            border: 1px solid var(--border-subtle);
            color: var(--text-secondary);
            padding: 7px 13px;
            border-radius: 7px;
            font-size: 12px;
            font-weight: 500;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 6px;
            transition: all 0.15s ease;
        }

        .workflow-btn:hover {
            background: var(--bg-subtle);
            color: var(--text-primary);
            border-color: var(--border-strong);
            transform: translateY(-1px);
        }

        .user-section {
            display: flex;
            align-items: center;
            gap: 16px;
        }

        .core-status {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 5px 12px;
            background: rgba(16, 185, 129, 0.08);
            border: 1px solid rgba(16, 185, 129, 0.2);
            border-radius: 20px;
            font-size: 12px;
            font-weight: 500;
            color: var(--success);
        }

        .pulse-dot {
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background: var(--success);
            box-shadow: 0 0 8px var(--success);
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0% { transform: scale(0.95); opacity: 0.8; }
            50% { transform: scale(1.15); opacity: 1; }
            100% { transform: scale(0.95); opacity: 0.8; }
        }

        .user-pill {
            display: flex;
            align-items: center;
            gap: 8px;
            background: var(--bg-elevated);
            padding: 4px 10px 4px 5px;
            border-radius: 20px;
            border: 1px solid var(--border-subtle);
            font-size: 12px;
            color: var(--text-primary);
        }

        .avatar-sm {
            width: 24px;
            height: 24px;
            border-radius: 50%;
            background: linear-gradient(135deg, #4f46e5, #06b6d4);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 10px;
            font-weight: 700;
            color: white;
        }

        /* Main 2-Pane Workspace */
        .workspace {
            display: grid;
            grid-template-columns: 1fr 400px;
            flex: 1;
            height: calc(100vh - 61px);
            overflow: hidden;
        }

        /* Left: Operations Console */
        .console-panel {
            display: flex;
            flex-direction: column;
            border-right: 1px solid var(--border-subtle);
            background: var(--bg-base);
            position: relative;
        }

        .console-scroll {
            flex: 1;
            overflow-y: auto;
            padding: 24px 32px;
            display: flex;
            flex-direction: column;
            gap: 20px;
        }

        /* Executive Header Banner */
        .executive-hero {
            background: linear-gradient(180deg, var(--bg-surface) 0%, rgba(17, 20, 31, 0.4) 100%);
            border: 1px solid var(--border-subtle);
            border-radius: 12px;
            padding: 20px 24px;
            box-shadow: var(--shadow-sm);
        }

        .hero-top {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 12px;
        }

        .hero-top h2 {
            font-family: 'Outfit', sans-serif;
            font-size: 20px;
            font-weight: 700;
            color: var(--text-primary);
            letter-spacing: -0.02em;
        }

        .hero-badge {
            background: var(--accent-soft);
            color: #a5b4fc;
            border: 1px solid rgba(99, 102, 241, 0.3);
            font-size: 11px;
            font-weight: 600;
            padding: 3px 8px;
            border-radius: 4px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .hero-desc {
            font-size: 13px;
            color: var(--text-secondary);
            line-height: 1.5;
            max-width: 680px;
            margin-bottom: 18px;
        }

        .kpi-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 12px;
        }

        .kpi-card {
            background: var(--bg-elevated);
            border: 1px solid var(--border-subtle);
            padding: 12px 14px;
            border-radius: 8px;
        }

        .kpi-card .val {
            font-family: 'Outfit', sans-serif;
            font-size: 18px;
            font-weight: 700;
            color: #ffffff;
            display: block;
            margin-bottom: 2px;
        }

        .kpi-card .lbl {
            font-size: 11px;
            color: var(--text-muted);
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }

        /* Message Bubbles */
        .message-row {
            display: flex;
            gap: 14px;
            max-width: 820px;
        }

        .message-row.user {
            align-self: flex-end;
            flex-direction: row-reverse;
        }

        .message-avatar {
            width: 32px;
            height: 32px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 13px;
            font-weight: 700;
            flex-shrink: 0;
        }

        .message-row.assistant .message-avatar {
            background: linear-gradient(135deg, #6366f1, #8b5cf6);
            color: white;
            box-shadow: 0 0 10px rgba(99, 102, 241, 0.3);
        }

        .message-row.user .message-avatar {
            background: var(--bg-subtle);
            color: var(--text-primary);
            border: 1px solid var(--border-strong);
        }

        .message-content {
            background: var(--bg-surface);
            border: 1px solid var(--border-subtle);
            border-radius: 12px;
            padding: 16px 20px;
            font-size: 14px;
            line-height: 1.6;
            color: var(--text-primary);
            box-shadow: var(--shadow-sm);
            width: 100%;
        }

        .message-row.user .message-content {
            background: #1e1b4b;
            border-color: rgba(99, 102, 241, 0.3);
            color: #f1f5f9;
        }

        .message-content h3 {
            font-size: 14px;
            font-weight: 700;
            color: #ffffff;
            margin: 8px 0 6px 0;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .message-content p {
            margin-bottom: 8px;
        }

        .message-content p:last-child {
            margin-bottom: 0;
        }

        .message-content ul {
            margin: 6px 0 10px 18px;
        }

        .message-content li {
            margin-bottom: 4px;
        }

        .message-content blockquote {
            border-left: 3px solid var(--accent);
            padding-left: 12px;
            color: var(--text-secondary);
            margin: 6px 0 8px 0;
            font-style: italic;
        }

        .message-content code {
            font-family: var(--font-mono);
            font-size: 12px;
            background: var(--bg-subtle);
            padding: 2px 6px;
            border-radius: 4px;
            color: #c7d2fe;
        }

        /* Shimmer Status Indicator */
        .status-shimmer {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 10px 16px;
            background: var(--bg-surface);
            border: 1px solid var(--border-subtle);
            border-radius: 8px;
            font-size: 13px;
            color: var(--text-secondary);
            align-self: flex-start;
            margin-left: 46px;
        }

        .status-spinner {
            width: 14px;
            height: 14px;
            border: 2px solid rgba(99, 102, 241, 0.2);
            border-top-color: var(--accent);
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        /* Approval Card */
        .approval-card {
            background: rgba(30, 27, 75, 0.5);
            border: 1px solid rgba(99, 102, 241, 0.4);
            border-radius: 10px;
            padding: 18px 20px;
            margin-top: 10px;
        }

        .approval-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 10px;
        }

        .approval-badge {
            background: rgba(245, 158, 11, 0.15);
            border: 1px solid rgba(245, 158, 11, 0.3);
            color: #fbbf24;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            padding: 2px 8px;
            border-radius: 4px;
        }

        .approval-steps {
            list-style: none;
            margin: 12px 0;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .approval-step-item {
            background: var(--bg-surface);
            border: 1px solid var(--border-subtle);
            padding: 8px 12px;
            border-radius: 6px;
            font-size: 13px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .approval-actions {
            display: flex;
            gap: 10px;
            margin-top: 14px;
        }

        .btn-approve {
            background: var(--success);
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: opacity 0.15s;
        }

        .btn-approve:hover { opacity: 0.9; }

        .btn-reject {
            background: var(--bg-subtle);
            border: 1px solid var(--border-subtle);
            color: var(--text-secondary);
            padding: 8px 14px;
            border-radius: 6px;
            font-size: 13px;
            cursor: pointer;
        }

        .btn-reject:hover { background: var(--bg-elevated); color: var(--text-primary); }

        /* Prompt Bar */
        .prompt-container {
            padding: 16px 32px 20px 32px;
            background: var(--bg-surface);
            border-top: 1px solid var(--border-subtle);
            display: flex;
            flex-direction: column;
            gap: 10px;
        }

        .quick-suggestions {
            display: flex;
            align-items: center;
            gap: 8px;
            overflow-x: auto;
            scrollbar-width: none;
        }

        .suggestion-chip {
            background: var(--bg-elevated);
            border: 1px solid var(--border-subtle);
            padding: 5px 11px;
            border-radius: 16px;
            font-size: 12px;
            color: var(--text-secondary);
            cursor: pointer;
            white-space: nowrap;
            transition: all 0.15s;
        }

        .suggestion-chip:hover {
            background: var(--bg-subtle);
            color: var(--text-primary);
            border-color: var(--border-strong);
        }

        .input-bar {
            display: flex;
            align-items: center;
            background: var(--bg-base);
            border: 1px solid var(--border-subtle);
            border-radius: 10px;
            padding: 4px 6px 4px 14px;
            transition: border-color 0.15s, box-shadow 0.15s;
        }

        .input-bar:focus-within {
            border-color: var(--accent);
            box-shadow: 0 0 0 2px var(--accent-soft);
        }

        .input-bar input {
            flex: 1;
            background: transparent;
            border: none;
            color: var(--text-primary);
            font-size: 14px;
            font-family: inherit;
            outline: none;
            padding: 8px 0;
        }

        .btn-send {
            background: var(--accent);
            color: white;
            border: none;
            padding: 8px 18px;
            border-radius: 7px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: background 0.15s;
        }

        .btn-send:hover { background: var(--accent-hover); }
        .btn-send:disabled { opacity: 0.5; cursor: not-allowed; }

        /* Right Panel: Governance & Audit */
        .audit-panel {
            background: var(--bg-surface);
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        .audit-header {
            padding: 16px 20px;
            border-bottom: 1px solid var(--border-subtle);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .audit-header h2 {
            font-family: 'Outfit', sans-serif;
            font-size: 14px;
            font-weight: 700;
            letter-spacing: -0.01em;
            color: var(--text-primary);
            text-transform: uppercase;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .audit-tabs {
            display: flex;
            border-bottom: 1px solid var(--border-subtle);
            background: var(--bg-base);
        }

        .audit-tab {
            flex: 1;
            padding: 10px 12px;
            font-size: 12px;
            font-weight: 600;
            color: var(--text-muted);
            background: transparent;
            border: none;
            cursor: pointer;
            text-align: center;
            border-bottom: 2px solid transparent;
            transition: all 0.15s;
        }

        .audit-tab.active {
            color: var(--text-primary);
            border-bottom-color: var(--accent);
            background: var(--bg-surface);
        }

        .audit-content {
            flex: 1;
            overflow-y: auto;
            padding: 16px 20px;
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        /* Agents & Guardrails Tab */
        .agent-card {
            background: var(--bg-elevated);
            border: 1px solid var(--border-subtle);
            border-radius: 8px;
            padding: 12px 14px;
        }

        .agent-top {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 6px;
        }

        .agent-name {
            font-size: 13px;
            font-weight: 600;
            color: #ffffff;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .agent-badge {
            font-size: 10px;
            font-weight: 700;
            text-transform: uppercase;
            padding: 2px 6px;
            border-radius: 4px;
        }

        .badge-active {
            background: var(--success-soft);
            color: var(--success);
            border: 1px solid rgba(16, 185, 129, 0.25);
        }

        .agent-scope {
            font-size: 11px;
            color: var(--text-secondary);
            line-height: 1.4;
        }

        /* Trace Cards */
        .trace-card {
            background: var(--bg-elevated);
            border: 1px solid var(--border-subtle);
            border-radius: 8px;
            padding: 12px 14px;
            font-size: 12px;
        }

        .trace-card-top {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 8px;
        }

        .radar-bar {
            height: 5px;
            background: var(--bg-subtle);
            border-radius: 3px;
            overflow: hidden;
            margin-top: 4px;
        }

        .radar-fill {
            height: 100%;
            background: var(--accent);
            border-radius: 3px;
        }

        /* Scrollbars */
        ::-webkit-scrollbar { width: 5px; height: 5px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: var(--bg-subtle); border-radius: 4px; }
    </style>
</head>
<body>

    <!-- Top Enterprise Navigation -->
    <header class="top-nav">
        <div class="brand-section">
            <div class="brand-logo">T</div>
            <div class="brand-text">
                <h1>THIRA</h1>
                <p>Enterprise Autonomous Operations</p>
            </div>
            <div class="workspace-tag">
                <span>🏢</span>
                <span>Acme Global · Executive Suite</span>
            </div>
        </div>

        <div class="action-workflows">
            <button class="workflow-btn" onclick="triggerWorkflow('executive_briefing')">
                <span>📊</span> Executive Briefing
            </button>
            <button class="workflow-btn" onclick="triggerWorkflow('schedule_sync')">
                <span>📅</span> Schedule Review
            </button>
            <button class="workflow-btn" onclick="triggerWorkflow('inbound_rfp')">
                <span>✉️</span> Priority Inbox
            </button>
            <button class="workflow-btn" onclick="triggerWorkflow('governance_audit')">
                <span>🛡️</span> Governance Audit
            </button>
        </div>

        <div class="user-section">
            <div class="core-status">
                <div class="pulse-dot"></div>
                <span id="coreStatusText">Core Active · L3 Policy</span>
            </div>
            <div class="user-pill">
                <div class="avatar-sm">SG</div>
                <span>Shivansh Gautam</span>
            </div>
        </div>
    </header>

    <!-- 2-Pane Main Layout -->
    <main class="workspace">

        <!-- Left: Operations Console -->
        <section class="console-panel">
            <div class="console-scroll" id="messagesContainer">

                <!-- Executive Welcome Card -->
                <div class="executive-hero">
                    <div class="hero-top">
                        <h2>Executive Operations Console</h2>
                        <span class="hero-badge">L3 Autonomous Governance</span>
                    </div>
                    <p class="hero-desc">
                        THIRA is actively monitoring executive communications, calendar schedules, and enterprise agents. All actions adhere to strict deterministic safety policies and deterministic verification.
                    </p>
                    <div class="kpi-grid">
                        <div class="kpi-card">
                            <span class="val">4 Active</span>
                            <span class="lbl">Specialized Agents</span>
                        </div>
                        <div class="kpi-card">
                            <span class="val">100%</span>
                            <span class="lbl">Audit Integrity</span>
                        </div>
                        <div class="kpi-card">
                            <span class="val">L3 Guard</span>
                            <span class="lbl">Safety Policy</span>
                        </div>
                        <div class="kpi-card">
                            <span class="val">ECHO</span>
                            <span class="lbl">Causal Memory</span>
                        </div>
                    </div>
                </div>

                <!-- Initial Copilot Message -->
                <div class="message-row assistant">
                    <div class="message-avatar">T</div>
                    <div class="message-content">
                        <strong>Good morning, Shivansh.</strong><br>
                        I am THIRA, your autonomous operations copilot. I am actively tracking your schedule, prioritizing client inquiries, and preparing draft responses under enterprise governance policies.<br><br>
                        You can ask: <em>"What's on my schedule today?"</em>, request a <em>"Priority inbox summary"</em>, or select an executive workflow from the top bar.
                    </div>
                </div>

            </div>

            <!-- Shimmer placeholder (hidden by default) -->
            <div id="shimmerHolder" style="display: none; padding: 0 32px 10px 32px;">
                <div class="status-shimmer">
                    <div class="status-spinner"></div>
                    <span id="shimmerText">Coordinating specialized agents & synthesizing briefing...</span>
                </div>
            </div>

            <!-- Prompt & Input Bar -->
            <footer class="prompt-container">
                <div class="quick-suggestions">
                    <div class="suggestion-chip" onclick="sendQuickPrompt('What is on my schedule today?')">
                        📅 What's on my schedule today?
                    </div>
                    <div class="suggestion-chip" onclick="sendQuickPrompt('Triage high-priority emails and prepare drafts')">
                        ✉️ Triage priority inbox
                    </div>
                    <div class="suggestion-chip" onclick="sendQuickPrompt('Generate my morning executive briefing')">
                        🌅 Morning executive briefing
                    </div>
                    <div class="suggestion-chip" onclick="sendQuickPrompt('Audit active agent security policies and permissions')">
                        🛡️ Governance & safety audit
                    </div>
                </div>

                <div class="input-bar">
                    <input type="text" id="commandInput" placeholder="Instruct THIRA or ask for an executive briefing..." autocomplete="off" autofocus>
                    <button class="btn-send" id="sendBtn" onclick="handleSend()">Send</button>
                </div>
            </footer>
        </section>

        <!-- Right: Governance & Audit -->
        <aside class="audit-panel">
            <div class="audit-header">
                <h2>🛡️ Governance & Audit</h2>
                <span style="font-size: 11px; color: var(--text-muted); font-family: var(--font-mono);" id="activeTraceBadge">CORE READY</span>
            </div>

            <div class="audit-tabs">
                <button class="audit-tab active" id="tabAgents" onclick="switchTab('agents')">Agent Guardrails</button>
                <button class="audit-tab" id="tabTrace" onclick="switchTab('trace')">Decision Radar</button>
            </div>

            <div class="audit-content" id="auditContent">
                <!-- Guardrails Tab Content -->
                <div id="guardrailsView" style="display: flex; flex-direction: column; gap: 12px;">
                    <div class="agent-card">
                        <div class="agent-top">
                            <span class="agent-name">✉️ Gmail Agent</span>
                            <span class="agent-badge badge-active">Operational</span>
                        </div>
                        <p class="agent-scope">
                            <strong>Permissions</strong>: Read, triage & draft.<br>
                            <strong>Policy</strong>: Autonomous drafting; explicit human authorization required for external sends.
                        </p>
                    </div>

                    <div class="agent-card">
                        <div class="agent-top">
                            <span class="agent-name">📅 Calendar Agent</span>
                            <span class="agent-badge badge-active">Operational</span>
                        </div>
                        <p class="agent-scope">
                            <strong>Permissions</strong>: Read events, detect conflicts & draft invites.<br>
                            <strong>Policy</strong>: L3 Guardrails active; client invite dispatch gated on confirmation.
                        </p>
                    </div>

                    <div class="agent-card">
                        <div class="agent-top">
                            <span class="agent-name">📁 Filesystem Agent</span>
                            <span class="agent-badge badge-active">Operational</span>
                        </div>
                        <p class="agent-scope">
                            <strong>Permissions</strong>: Workspace read & artifact generation.<br>
                            <strong>Policy</strong>: Strictly sandboxed to project directory.
                        </p>
                    </div>

                    <div class="agent-card">
                        <div class="agent-top">
                            <span class="agent-name">💻 Terminal Agent</span>
                            <span class="agent-badge badge-active">Guarded</span>
                        </div>
                        <p class="agent-scope">
                            <strong>Permissions</strong>: Restricted local commands.<br>
                            <strong>Policy</strong>: L4 policy enforcement; destructive commands blocked.
                        </p>
                    </div>

                    <div style="background: rgba(99, 102, 241, 0.08); border: 1px solid rgba(99, 102, 241, 0.2); border-radius: 8px; padding: 12px; margin-top: 4px;">
                        <span style="font-size: 11px; font-weight: 700; color: #a5b4fc; text-transform: uppercase;">Deterministic Guarantee</span>
                        <p style="font-size: 11px; color: var(--text-secondary); margin-top: 4px; line-height: 1.4;">
                            Every autonomous step is verified with pre/post condition assertions and recorded to ECHO semantic memory.
                        </p>
                    </div>
                </div>

                <!-- Trace Feed View (Hidden initially) -->
                <div id="traceView" style="display: none; flex-direction: column; gap: 12px;">
                    <div id="decisionRadarBox" class="trace-card" style="display: none;">
                        <div class="trace-card-top">
                            <strong>🎯 Decision Radar</strong>
                            <span style="color: var(--success); font-size: 11px; font-weight: 600;" id="radarAction">ACT</span>
                        </div>
                        <div style="display: flex; flex-direction: column; gap: 6px; margin-top: 6px;">
                            <div>
                                <div style="display: flex; justify-content: space-between; font-size: 11px; color: var(--text-muted);">
                                    <span>Importance</span><span id="radarImp">90%</span>
                                </div>
                                <div class="radar-bar"><div class="radar-fill" id="radarImpBar" style="width: 90%;"></div></div>
                            </div>
                            <div>
                                <div style="display: flex; justify-content: space-between; font-size: 11px; color: var(--text-muted);">
                                    <span>Urgency</span><span id="radarUrg">85%</span>
                                </div>
                                <div class="radar-bar"><div class="radar-fill" id="radarUrgBar" style="width: 85%; background: var(--warning);"></div></div>
                            </div>
                            <div>
                                <div style="display: flex; justify-content: space-between; font-size: 11px; color: var(--text-muted);">
                                    <span>Safety Confidence</span><span id="radarConf">95%</span>
                                </div>
                                <div class="radar-bar"><div class="radar-fill" id="radarConfBar" style="width: 95%; background: var(--success);"></div></div>
                            </div>
                        </div>
                    </div>

                    <div id="traceStream">
                        <div style="color: var(--text-muted); font-size: 12px; text-align: center; margin-top: 30px;">
                            Awaiting orchestrator events...
                        </div>
                    </div>
                </div>
            </div>
        </aside>

    </main>

    <script>
        const messagesDiv = document.getElementById('messagesContainer');
        const input = document.getElementById('commandInput');
        const sendBtn = document.getElementById('sendBtn');
        const statusText = document.getElementById('coreStatusText');
        const activeTraceBadge = document.getElementById('activeTraceBadge');
        const shimmerHolder = document.getElementById('shimmerHolder');
        const shimmerText = document.getElementById('shimmerText');

        let ws = null;

        function connect() {
            const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${protocol}//${location.host}/ws/chat`);

            ws.onopen = () => {
                statusText.textContent = 'Core Active · L3 Policy';
                sendBtn.disabled = false;
            };

            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                handlePayload(data);
            };

            ws.onclose = () => {
                statusText.textContent = 'Reconnecting...';
                sendBtn.disabled = true;
                setTimeout(connect, 3000);
            };

            ws.onerror = () => {
                statusText.textContent = 'Offline';
            };
        }

        function handlePayload(data) {
            if (data.type === 'trace') {
                renderTrace(data.stage, data.data);
            } else if (data.type === 'status') {
                showShimmer(data.message || 'Processing with autonomous agents...');
            } else if (data.type === 'response') {
                hideShimmer();
                addAssistantMessage(data.message);
                if (data.trace_id) {
                    activeTraceBadge.textContent = data.trace_id.slice(-8).toUpperCase();
                }
            } else if (data.type === 'approval_request') {
                hideShimmer();
                renderApprovalCard(data);
            } else if (data.type === 'notification') {
                // non-intrusive notification
                console.log('Notification:', data.message);
            } else if (data.type === 'error') {
                hideShimmer();
                addAssistantMessage(`⚠️ **System Notice**: ${data.message}`);
            }
        }

        function showShimmer(text) {
            shimmerText.textContent = text;
            shimmerHolder.style.display = 'block';
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }

        function hideShimmer() {
            shimmerHolder.style.display = 'none';
        }

        function parseMarkdown(text) {
            if (!text) return '';
            let html = text
                .replace(/### (.*?)\\n/g, '<h3>$1</h3>')
                .replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>')
                .replace(/\\*(.*?)\\*/g, '<em>$1</em>')
                .replace(/`([^`]+)`/g, '<code>$1</code>')
                .replace(/^> (.*?)$/gm, '<blockquote>$1</blockquote>')
                .replace(/^• (.*?)$/gm, '<li>$1</li>')
                .replace(/\\n\\n/g, '<br><br>')
                .replace(/\\n/g, '<br>');

            // Wrap list items
            if (html.includes('<li>')) {
                html = html.replace(/(<li>.*?<\\/li>)/g, '<ul>$1</ul>');
            }
            return html;
        }

        function addAssistantMessage(rawText) {
            const row = document.createElement('div');
            row.className = 'message-row assistant';
            row.innerHTML = `
                <div class="message-avatar">T</div>
                <div class="message-content">${parseMarkdown(rawText)}</div>
            `;
            messagesDiv.appendChild(row);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }

        function addUserMessage(text) {
            const row = document.createElement('div');
            row.className = 'message-row user';
            row.innerHTML = `
                <div class="message-avatar">SG</div>
                <div class="message-content">${text}</div>
            `;
            messagesDiv.appendChild(row);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }

        function renderApprovalCard(data) {
            const row = document.createElement('div');
            row.className = 'message-row assistant';
            row.id = `approval_row_${data.plan_id}`;

            let stepsHtml = '';
            if (data.steps_requiring_approval) {
                stepsHtml = data.steps_requiring_approval.map(s => `
                    <li class="approval-step-item">
                        <span><strong>${s.agent}</strong> · ${s.tool}</span>
                        <span style="color: var(--text-muted); font-size: 11px;">${s.description}</span>
                    </li>
                `).join('');
            }

            row.innerHTML = `
                <div class="message-avatar">T</div>
                <div class="message-content">
                    <div class="approval-card" id="card_${data.plan_id}">
                        <div class="approval-header">
                            <strong>${data.message || 'Authorization Required'}</strong>
                            <span class="approval-badge">L3 Clearance</span>
                        </div>
                        <p style="font-size: 12px; color: var(--text-secondary); margin-bottom: 8px;">
                            THIRA requires your explicit authorization before dispatching this external-facing action:
                        </p>
                        <ul class="approval-steps">${stepsHtml}</ul>
                        <div class="approval-actions">
                            <button class="btn-approve" onclick="resolveApproval('${data.plan_id}', true)">Authorize & Execute</button>
                            <button class="btn-reject" onclick="resolveApproval('${data.plan_id}', false)">Decline</button>
                        </div>
                    </div>
                </div>
            `;
            messagesDiv.appendChild(row);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }

        async function resolveApproval(planId, approved) {
            const card = document.getElementById(`card_${planId}`);
            if (card) {
                card.style.opacity = '0.7';
                card.innerHTML = `<div style="font-weight: 600; color: ${approved ? 'var(--success)' : 'var(--danger)'};">
                    ${approved ? '✓ Plan Authorized' : '✗ Plan Declined'} — Resuming execution...
                </div>`;
            }
            try {
                await fetch(`/api/approve/${planId}?approved=${approved}`, { method: 'POST' });
            } catch (e) {
                console.error(e);
            }
        }

        function handleSend() {
            const message = input.value.trim();
            if (!message || !ws) return;

            addUserMessage(message);
            showShimmer('Evaluating request and coordinating agents...');
            ws.send(JSON.stringify({ message }));
            input.value = '';
        }

        function sendQuickPrompt(promptText) {
            input.value = promptText;
            handleSend();
        }

        async function triggerWorkflow(workflowName) {
            showShimmer(`Initiating ${workflowName.replace('_', ' ')}...`);
            switchTab('trace');
            try {
                await fetch(`/api/scenarios/demo/${workflowName}`, { method: 'POST' });
            } catch (e) {
                console.error(e);
            }
        }

        function switchTab(tabName) {
            const tabAgents = document.getElementById('tabAgents');
            const tabTrace = document.getElementById('tabTrace');
            const guardrailsView = document.getElementById('guardrailsView');
            const traceView = document.getElementById('traceView');

            if (tabName === 'agents') {
                tabAgents.classList.add('active');
                tabTrace.classList.remove('active');
                guardrailsView.style.display = 'flex';
                traceView.style.display = 'none';
            } else {
                tabTrace.classList.add('active');
                tabAgents.classList.remove('active');
                guardrailsView.style.display = 'none';
                traceView.style.display = 'flex';
            }
        }

        function renderTrace(stage, data) {
            if (data.trace_id) {
                activeTraceBadge.textContent = data.trace_id.slice(-8).toUpperCase();
            }

            const stream = document.getElementById('traceStream');
            if (stream.children.length === 1 && stream.children[0].innerText.includes('Awaiting')) {
                stream.innerHTML = '';
            }

            if (stage === 'decision') {
                const radarBox = document.getElementById('decisionRadarBox');
                radarBox.style.display = 'block';
                document.getElementById('radarAction').textContent = (data.action || 'ACT').toUpperCase();
                const imp = Math.round((data.importance || 0.8) * 100);
                const urg = Math.round((data.urgency || 0.7) * 100);
                const conf = Math.round((data.confidence || 0.9) * 100);
                document.getElementById('radarImp').textContent = `${imp}%`;
                document.getElementById('radarImpBar').style.width = `${imp}%`;
                document.getElementById('radarUrg').textContent = `${urg}%`;
                document.getElementById('radarUrgBar').style.width = `${urg}%`;
                document.getElementById('radarConf').textContent = `${conf}%`;
                document.getElementById('radarConfBar').style.width = `${conf}%`;
            }

            const card = document.createElement('div');
            card.className = 'trace-card';
            card.innerHTML = `
                <div class="trace-card-top">
                    <strong style="text-transform: uppercase; font-size: 11px; color: var(--accent);">${stage}</strong>
                    <span style="font-size: 10px; color: var(--text-muted);">${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
                </div>
                <div style="font-size: 11px; color: var(--text-secondary); line-height: 1.4;">
                    ${data.summary || data.goal || data.reasoning || data.source || 'Stage completed successfully.'}
                </div>
            `;
            stream.prepend(card);
        }

        input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') handleSend();
        });

        connect();
    </script>
</body>
</html>"""
