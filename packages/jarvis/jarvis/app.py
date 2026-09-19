"""JARVIS FastAPI application — the web server powering the human interface."""

from __future__ import annotations

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
    logger.info("jarvis.starting")
    if _orchestrator is None:
        try:
            from main import create_thira

            _orchestrator = await create_thira()
            logger.info("jarvis.orchestrator_auto_initialized")
        except Exception as e:
            logger.warning("jarvis.auto_init_skipped", reason=str(e))
    yield
    logger.info("jarvis.stopping")


app = FastAPI(
    title="THIRA — Autonomous Intelligence Platform",
    description="The human-facing interface of the THIRA agentic intelligence platform.",
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
        logger.info("jarvis.ws_connected", total=len(self.active_connections))

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info("jarvis.ws_disconnected", total=len(self.active_connections))

    async def broadcast(self, message: dict):
        """Broadcast a message to all connected clients."""
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                pass


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

            logger.info("jarvis.message_received", message=message[:100])

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
                        "message": "THIRA loop engaged...",
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
                "message": f"I need your approval for: {authorized_plan.plan.goal}",
            }
        )
        logger.info("jarvis.approval_requested", plan_id=plan_id)

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


# ─── REST API & Demo Endpoints ───────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the JARVIS cognitive chat UI."""
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
    """Trigger a pre-canned executive scenario for demoing THIRA's capabilities."""
    if not _orchestrator:
        return {"error": "Orchestrator not initialized"}

    if scenario_name == "morning_briefing":
        event = ThiraEvent(
            source=EventSource.USER_COMMAND,
            type=EventType.USER_REQUEST,
            timestamp=datetime.now(UTC),
            actor="user",
            content="Generate my morning executive briefing. Review upcoming calendar events and summarize priority items.",
        )
    elif scenario_name == "inbound_email":
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
    elif scenario_name == "schedule_check":
        event = ThiraEvent(
            source=EventSource.CALENDAR,
            type=EventType.CALENDAR_EVENT_UPCOMING,
            timestamp=datetime.now(UTC),
            actor="calendar",
            content="Calendar Alert: Engineering Architecture Sync is starting in 15 minutes.",
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


# ─── Chat UI HTML + Live Trace Dashboard ─────────────────────

CHAT_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>THIRA — Autonomous Platform</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }

        :root {
            --bg-primary: #0b0c10;
            --bg-secondary: #13151f;
            --bg-tertiary: #1b1e2e;
            --surface-hover: #24283d;
            --text-primary: #f1f3f9;
            --text-secondary: #9499b3;
            --accent: #6366f1;
            --accent-glow: rgba(99, 102, 241, 0.25);
            --success: #10b981;
            --success-bg: rgba(16, 185, 129, 0.15);
            --warning: #f59e0b;
            --warning-bg: rgba(245, 158, 11, 0.15);
            --error: #ef4444;
            --border: #232738;
            --font-mono: 'JetBrains Mono', monospace;
        }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            height: 100vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        /* Top Header */
        .header {
            padding: 14px 24px;
            border-bottom: 1px solid var(--border);
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: var(--bg-secondary);
            flex-shrink: 0;
        }

        .header-left {
            display: flex;
            align-items: center;
            gap: 14px;
        }

        .header .logo {
            width: 36px;
            height: 36px;
            background: linear-gradient(135deg, #6366f1, #a855f7);
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 16px;
            box-shadow: 0 0 16px var(--accent-glow);
        }

        .header h1 {
            font-size: 17px;
            font-weight: 700;
            letter-spacing: -0.01em;
            background: linear-gradient(135deg, #ffffff, #a5b4fc);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .header-demos {
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .demo-pill {
            background: var(--bg-tertiary);
            border: 1px solid var(--border);
            color: var(--text-secondary);
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s ease;
        }

        .demo-pill:hover {
            background: var(--surface-hover);
            color: var(--text-primary);
            border-color: var(--accent);
            transform: translateY(-1px);
        }

        .header-right {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .status-badge {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 12px;
            color: var(--text-secondary);
            background: var(--bg-primary);
            padding: 6px 12px;
            border-radius: 20px;
            border: 1px solid var(--border);
        }

        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--success);
            box-shadow: 0 0 8px var(--success);
            animation: pulse 2s ease-in-out infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.5; transform: scale(0.9); }
        }

        /* Workspace Grid: Chat (Left) + Trace Panel (Right) */
        .workspace {
            display: grid;
            grid-template-columns: 1fr 420px;
            flex: 1;
            height: calc(100vh - 65px);
            overflow: hidden;
        }

        /* Chat Panel */
        .chat-panel {
            display: flex;
            flex-direction: column;
            border-right: 1px solid var(--border);
            background: var(--bg-primary);
            height: 100%;
        }

        .messages-container {
            flex: 1;
            overflow-y: auto;
            padding: 24px;
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        .message {
            max-width: 82%;
            padding: 14px 18px;
            border-radius: 14px;
            font-size: 14px;
            line-height: 1.6;
            animation: fadeIn 0.25s ease-out;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(6px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .message.user {
            align-self: flex-end;
            background: linear-gradient(135deg, #4f46e5, #6366f1);
            color: white;
            border-bottom-right-radius: 4px;
            box-shadow: 0 4px 16px rgba(79, 70, 229, 0.25);
        }

        .message.assistant {
            align-self: flex-start;
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-bottom-left-radius: 4px;
        }

        .message.status {
            align-self: center;
            background: transparent;
            color: var(--text-secondary);
            font-size: 12px;
            font-family: var(--font-mono);
            padding: 4px 12px;
        }

        .message.approval {
            align-self: flex-start;
            background: var(--bg-secondary);
            border: 1px solid var(--warning);
            border-radius: 14px;
            box-shadow: 0 0 20px rgba(245, 158, 11, 0.15);
            max-width: 90%;
        }

        .approval-header {
            display: flex;
            align-items: center;
            gap: 8px;
            font-weight: 600;
            color: var(--warning);
            margin-bottom: 8px;
        }

        .approval-steps {
            background: var(--bg-primary);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 10px 14px;
            margin: 10px 0;
            list-style: none;
            font-size: 13px;
        }

        .approval-steps li {
            margin-bottom: 6px;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .approval-steps li:last-child { margin-bottom: 0; }

        .approval-actions {
            display: flex;
            gap: 10px;
            margin-top: 12px;
        }

        .btn-approve {
            background: var(--success);
            color: white;
            border: none;
            padding: 8px 18px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }

        .btn-approve:hover { filter: brightness(1.1); transform: translateY(-1px); }

        .btn-reject {
            background: var(--bg-tertiary);
            color: var(--error);
            border: 1px solid var(--border);
            padding: 8px 18px;
            border-radius: 8px;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }

        .btn-reject:hover { background: rgba(239, 68, 68, 0.15); border-color: var(--error); }

        /* Chat Input */
        .input-area {
            padding: 16px 24px;
            border-top: 1px solid var(--border);
            background: var(--bg-secondary);
        }

        .input-wrapper {
            display: flex;
            gap: 12px;
            align-items: center;
        }

        .input-wrapper input {
            flex: 1;
            padding: 13px 18px;
            border: 1px solid var(--border);
            border-radius: 12px;
            background: var(--bg-primary);
            color: var(--text-primary);
            font-size: 14px;
            outline: none;
            transition: all 0.2s;
        }

        .input-wrapper input:focus {
            border-color: var(--accent);
            box-shadow: 0 0 0 3px var(--accent-glow);
        }

        .btn-send {
            padding: 13px 24px;
            border: none;
            border-radius: 12px;
            background: var(--accent);
            color: white;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }

        .btn-send:hover { background: #4f46e5; transform: translateY(-1px); }
        .btn-send:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }

        /* Right Panel: Thinking Trace */
        .trace-panel {
            background: var(--bg-secondary);
            display: flex;
            flex-direction: column;
            overflow: hidden;
            height: 100%;
        }

        .trace-header {
            padding: 16px 20px;
            border-bottom: 1px solid var(--border);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .trace-header h2 {
            font-size: 14px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 8px;
            color: var(--text-primary);
        }

        .trace-id-badge {
            font-family: var(--font-mono);
            font-size: 11px;
            color: var(--text-secondary);
            background: var(--bg-tertiary);
            padding: 3px 8px;
            border-radius: 6px;
        }

        .trace-feed {
            flex: 1;
            overflow-y: auto;
            padding: 18px 20px;
            display: flex;
            flex-direction: column;
            gap: 14px;
        }

        /* Trace Stage Cards */
        .trace-card {
            background: var(--bg-tertiary);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 14px;
            animation: fadeIn 0.2s ease;
        }

        .trace-card.active {
            border-color: var(--accent);
            box-shadow: 0 0 14px var(--accent-glow);
        }

        .trace-title {
            display: flex;
            align-items: center;
            justify-content: space-between;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 8px;
            color: var(--text-secondary);
        }

        .badge-pill {
            font-size: 11px;
            padding: 2px 8px;
            border-radius: 10px;
            font-weight: 600;
        }

        .badge-act { background: var(--success-bg); color: var(--success); }
        .badge-ignore { background: rgba(148, 163, 184, 0.15); color: #94a3b8; }
        .badge-mail { background: rgba(99, 102, 241, 0.15); color: #818cf8; }
        .badge-cal { background: rgba(236, 72, 153, 0.15); color: #f472b6; }

        .score-radar {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 6px;
            margin: 10px 0;
        }

        .score-item {
            background: var(--bg-primary);
            padding: 6px 8px;
            border-radius: 6px;
            text-align: center;
        }

        .score-item .label { font-size: 10px; color: var(--text-secondary); }
        .score-item .val { font-size: 12px; font-weight: 700; color: var(--text-primary); font-family: var(--font-mono); }

        .plan-step-list {
            margin-top: 8px;
            display: flex;
            flex-direction: column;
            gap: 6px;
        }

        .plan-step-item {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 12px;
            background: var(--bg-primary);
            padding: 6px 10px;
            border-radius: 6px;
        }

        .step-check {
            width: 14px;
            height: 14px;
            border-radius: 50%;
            border: 1px solid var(--text-secondary);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 9px;
        }

        .step-check.done {
            background: var(--success);
            border-color: var(--success);
            color: white;
        }

        /* Scrollbars */
        ::-webkit-scrollbar { width: 5px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
    </style>
</head>
<body>

    <header class="header">
        <div class="header-left">
            <div class="logo">T</div>
            <div>
                <h1>THIRA</h1>
                <p style="font-size: 11px; color: var(--text-secondary);">Agentic Intelligence & Autonomous Execution</p>
            </div>
        </div>

        <div class="header-demos">
            <span style="font-size: 12px; color: var(--text-secondary); margin-right: 4px;">Demos:</span>
            <button class="demo-pill" onclick="triggerScenario('morning_briefing')">🌅 Morning Briefing</button>
            <button class="demo-pill" onclick="triggerScenario('inbound_email')">✉️ Inbound RFP Email</button>
            <button class="demo-pill" onclick="triggerScenario('schedule_check')">📅 Check Schedule</button>
        </div>

        <div class="header-right">
            <div class="status-badge">
                <div class="status-dot" id="statusDot"></div>
                <span id="statusText">Connecting...</span>
            </div>
        </div>
    </header>

    <div class="workspace">
        <!-- Left: Chat Panel -->
        <div class="chat-panel">
            <div class="messages-container" id="messages">
                <div class="message assistant">
                    <strong>Greetings. I am THIRA.</strong><br>
                    I continuously perceive your digital environment, build context, decide what matters, plan actions, and execute through specialized agents.<br><br>
                    Try asking: <em>"What's on my schedule today?"</em> or trigger a <strong>Demo Scenario</strong> from the header.
                </div>
            </div>

            <div class="input-area">
                <div class="input-wrapper">
                    <input type="text" id="messageInput" placeholder="Command THIRA or ask a question..." autocomplete="off" autofocus>
                    <button class="btn-send" id="sendBtn" onclick="sendMessage()">Send</button>
                </div>
            </div>
        </div>

        <!-- Right: Cognitive Trace Panel -->
        <div class="trace-panel">
            <div class="trace-header">
                <h2>⚡ Cognitive Trace</h2>
                <span class="trace-id-badge" id="activeTraceId">IDLE</span>
            </div>

            <div class="trace-feed" id="traceFeed">
                <div style="color: var(--text-secondary); font-size: 13px; text-align: center; margin-top: 40px;">
                    Trace stream is listening for orchestrator events...
                </div>
            </div>
        </div>
    </div>

    <script>
        const messagesDiv = document.getElementById('messages');
        const traceFeed = document.getElementById('traceFeed');
        const input = document.getElementById('messageInput');
        const sendBtn = document.getElementById('sendBtn');
        const statusDot = document.getElementById('statusDot');
        const statusText = document.getElementById('statusText');
        const activeTraceId = document.getElementById('activeTraceId');

        let ws = null;

        function connect() {
            const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${protocol}//${location.host}/ws/chat`);

            ws.onopen = () => {
                statusDot.style.background = 'var(--success)';
                statusText.textContent = 'THIRA Ready';
                sendBtn.disabled = false;
            };

            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                handlePayload(data);
            };

            ws.onclose = () => {
                statusDot.style.background = 'var(--error)';
                statusText.textContent = 'Disconnected';
                sendBtn.disabled = true;
                setTimeout(connect, 3000);
            };

            ws.onerror = () => {
                statusDot.style.background = 'var(--error)';
                statusText.textContent = 'Offline';
            };
        }

        function handlePayload(data) {
            if (data.type === 'trace') {
                renderTrace(data.stage, data.data);
            } else if (data.type === 'status') {
                addMessage(data.message, 'status');
            } else if (data.type === 'response') {
                addMessage(data.message, 'assistant');
            } else if (data.type === 'approval_request') {
                renderApprovalCard(data);
            } else if (data.type === 'notification') {
                addMessage(`🔔 ${data.message}`, 'status');
            } else if (data.type === 'error') {
                addMessage(`❌ ${data.message}`, 'assistant');
            }
        }

        function renderTrace(stage, data) {
            if (data.trace_id) {
                activeTraceId.textContent = data.trace_id.slice(-8);
            }

            // Remove placeholder if present
            if (traceFeed.children.length === 1 && traceFeed.children[0].tagName === 'DIV') {
                traceFeed.innerHTML = '';
            }

            const card = document.createElement('div');
            card.className = 'trace-card active';

            if (stage === 'perception') {
                const badgeClass = data.source === 'gmail' ? 'badge-mail' : data.source === 'calendar' ? 'badge-cal' : 'badge-act';
                card.innerHTML = `
                    <div class="trace-title">
                        <span>👁️ Perception</span>
                        <span class="badge-pill ${badgeClass}">${data.source.toUpperCase()}</span>
                    </div>
                    <div style="font-size: 12px; color: var(--text-primary);">${data.content}</div>
                `;
            } else if (stage === 'context') {
                const entityPills = (data.entities || []).map(e => `<span class="badge-pill badge-act">${e.name} (${e.type})</span>`).join(' ');
                card.innerHTML = `
                    <div class="trace-title">
                        <span>🧠 Context Engine</span>
                        <span class="badge-pill badge-act">Resolved</span>
                    </div>
                    <div style="margin-bottom: 6px;">${entityPills || '<span style="color:var(--text-secondary); font-size:11px;">No entities</span>'}</div>
                    <div style="font-size: 12px; color: var(--text-secondary);">${data.interpretation || ''}</div>
                `;
            } else if (stage === 'decision') {
                card.innerHTML = `
                    <div class="trace-title">
                        <span>⚖️ Decision</span>
                        <span class="badge-pill badge-act">${data.action.toUpperCase()}</span>
                    </div>
                    <div class="score-radar">
                        <div class="score-item"><div class="label">URGENCY</div><div class="val">${Math.round((data.urgency || 0)*100)}%</div></div>
                        <div class="score-item"><div class="label">IMPORTANCE</div><div class="val">${Math.round((data.importance || 0)*100)}%</div></div>
                        <div class="score-item"><div class="label">RISK</div><div class="val">${Math.round((data.risk || 0)*100)}%</div></div>
                    </div>
                    <div style="font-size: 12px; color: var(--text-secondary);">${data.reasoning || ''}</div>
                `;
            } else if (stage === 'plan') {
                const stepsHtml = (data.steps || []).map(s => `
                    <div class="plan-step-item" id="step_${data.trace_id}_${s.index}">
                        <div class="step-check" id="check_${data.trace_id}_${s.index}">○</div>
                        <span><strong>${s.agent}.${s.tool}</strong>: ${s.description}</span>
                    </div>
                `).join('');

                card.innerHTML = `
                    <div class="trace-title">
                        <span>📐 Execution Plan</span>
                        <span class="badge-pill badge-act">${(data.steps || []).length} STEPS</span>
                    </div>
                    <div style="font-size: 12px; font-weight:600; margin-bottom: 6px;">${data.goal}</div>
                    <div class="plan-step-list">${stepsHtml}</div>
                `;
            } else if (stage === 'step_result') {
                const checkEl = document.getElementById(`check_${data.trace_id}_${data.step_index}`);
                if (checkEl) {
                    checkEl.className = 'step-check done';
                    checkEl.textContent = '✓';
                }
                return;
            } else if (stage === 'echo') {
                const learningsHtml = (data.learnings || []).map(l => `<li>💡 ${l}</li>`).join('');
                card.innerHTML = `
                    <div class="trace-title">
                        <span>💾 ECHO Memory</span>
                        <span class="badge-pill badge-act">LEARNED</span>
                    </div>
                    <ul style="font-size: 12px; list-style:none; display:flex; flex-direction:column; gap:4px;">
                        ${learningsHtml || '<li>Experience recorded into pgvector memory</li>'}
                    </ul>
                `;
            }

            traceFeed.prepend(card);
        }

        function renderApprovalCard(data) {
            const div = document.createElement('div');
            div.className = 'message approval';
            div.id = `approval_${data.plan_id}`;

            const steps = data.steps_requiring_approval.map(
                s => `<li><strong>${s.agent}.${s.tool}</strong>: ${s.description}</li>`
            ).join('');

            div.innerHTML = `
                <div class="approval-header">⚠️ Authorization Required</div>
                <div>${data.message}</div>
                <ul class="approval-steps">${steps}</ul>
                <div class="approval-actions">
                    <button class="btn-approve" onclick="resolveApproval('${data.plan_id}', true)">Authorize & Execute</button>
                    <button class="btn-reject" onclick="resolveApproval('${data.plan_id}', false)">Decline</button>
                </div>
            `;
            messagesDiv.appendChild(div);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }

        async function resolveApproval(planId, approved) {
            const card = document.getElementById(`approval_${planId}`);
            if (card) {
                card.style.opacity = '0.6';
                card.innerHTML = `<strong>${approved ? '✓ Authorized' : '✗ Declined'}</strong>: Resuming loop...`;
            }
            try {
                await fetch(`/api/approve/${planId}?approved=${approved}`, { method: 'POST' });
            } catch (e) {
                console.error(e);
            }
        }

        async function triggerScenario(name) {
            addMessage(`▶ Triggering demo scenario: ${name.replace('_', ' ')}...`, 'status');
            try {
                await fetch(`/api/scenarios/demo/${name}`, { method: 'POST' });
            } catch (e) {
                console.error(e);
            }
        }

        function addMessage(text, type) {
            const div = document.createElement('div');
            div.className = `message ${type}`;
            div.innerHTML = text;
            messagesDiv.appendChild(div);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
            return div;
        }

        function sendMessage() {
            const message = input.value.trim();
            if (!message || !ws) return;

            addMessage(message, 'user');
            ws.send(JSON.stringify({ message }));
            input.value = '';
        }

        input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendMessage();
        });

        connect();
    </script>
</body>
</html>"""
