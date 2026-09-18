"""JARVIS FastAPI application — the web server powering the human interface."""

from __future__ import annotations

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
    logger.info("jarvis.starting")
    yield
    logger.info("jarvis.stopping")


app = FastAPI(
    title="JARVIS — THIRA Human Interface",
    description="The human-facing layer of the THIRA agentic intelligence platform.",
    version="0.1.0",
    lifespan=lifespan,
)


# ─── WebSocket Chat ──────────────────────────────────────────


class ConnectionManager:
    """Manages active WebSocket connections."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("jarvis.ws_connected", total=len(self.active_connections))

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info("jarvis.ws_disconnected", total=len(self.active_connections))

    async def broadcast(self, message: dict):
        """Broadcast a message to all connected clients."""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass


manager = ConnectionManager()


@app.websocket("/ws/chat")
async def chat_endpoint(websocket: WebSocket):
    """Main chat WebSocket endpoint.

    User sends messages → THIRA processes through full loop → responses stream back.
    """
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            message = data.get("message", "")

            if not message:
                continue

            logger.info("jarvis.message_received", message=message[:100])

            # Convert user message to ThiraEvent
            event = ThiraEvent(
                source=EventSource.USER_COMMAND,
                type=EventType.USER_REQUEST,
                timestamp=datetime.now(UTC),
                actor="user",
                content=message,
            )

            # Process through THIRA loop
            if _orchestrator:
                # Send "thinking" indicator
                await websocket.send_json(
                    {
                        "type": "status",
                        "status": "processing",
                        "message": "Processing your request...",
                    }
                )

                result = await _orchestrator.process_event(event)

                # Send result back
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


# ─── Approval Flow ───────────────────────────────────────────


class JarvisNotifier:
    """Handles notifications and approval requests from THIRA to the user."""

    def __init__(self, connection_manager: ConnectionManager):
        self._manager = connection_manager
        self._pending_approvals: dict[str, dict] = {}

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

    async def notify(self, message: str, level: str = "info") -> None:
        """Send a notification to the user."""
        await self._manager.broadcast(
            {
                "type": "notification",
                "level": level,
                "message": message,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )


# ─── REST API ────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the JARVIS chat UI."""
    return CHAT_HTML


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "jarvis", "timestamp": datetime.now(UTC).isoformat()}


@app.post("/api/approve/{plan_id}")
async def approve_plan(plan_id: str, approved: bool = True):
    """Approve or reject a pending plan."""
    if _orchestrator:
        import uuid

        result = await _orchestrator.handle_approval(uuid.UUID(plan_id), approved)
        return {"status": result.status, "plan_id": plan_id}
    return {"error": "Orchestrator not initialized"}


# ─── Chat UI HTML ────────────────────────────────────────────

CHAT_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>JARVIS — THIRA Interface</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }

        :root {
            --bg-primary: #0a0a0f;
            --bg-secondary: #12121a;
            --bg-tertiary: #1a1a2e;
            --text-primary: #e4e4ef;
            --text-secondary: #8888aa;
            --accent: #6366f1;
            --accent-glow: rgba(99, 102, 241, 0.3);
            --success: #22c55e;
            --warning: #f59e0b;
            --error: #ef4444;
            --border: #2a2a3e;
        }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            height: 100vh;
            display: flex;
            flex-direction: column;
        }

        /* Header */
        .header {
            padding: 16px 24px;
            border-bottom: 1px solid var(--border);
            display: flex;
            align-items: center;
            gap: 12px;
            background: var(--bg-secondary);
        }

        .header .logo {
            width: 32px;
            height: 32px;
            background: linear-gradient(135deg, var(--accent), #a855f7);
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 14px;
        }

        .header h1 {
            font-size: 18px;
            font-weight: 600;
            background: linear-gradient(135deg, var(--text-primary), var(--accent));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .header .status {
            margin-left: auto;
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 12px;
            color: var(--text-secondary);
        }

        .header .status .dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--success);
            animation: pulse 2s ease-in-out infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.4; }
        }

        /* Messages */
        .messages {
            flex: 1;
            overflow-y: auto;
            padding: 24px;
            display: flex;
            flex-direction: column;
            gap: 16px;
        }

        .message {
            max-width: 80%;
            padding: 12px 16px;
            border-radius: 12px;
            font-size: 14px;
            line-height: 1.6;
            animation: fadeIn 0.3s ease;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(8px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .message.user {
            align-self: flex-end;
            background: var(--accent);
            color: white;
            border-bottom-right-radius: 4px;
        }

        .message.assistant {
            align-self: flex-start;
            background: var(--bg-tertiary);
            border: 1px solid var(--border);
            border-bottom-left-radius: 4px;
        }

        .message.status {
            align-self: center;
            background: none;
            color: var(--text-secondary);
            font-size: 12px;
            padding: 4px 12px;
        }

        .message.approval {
            align-self: flex-start;
            background: var(--bg-tertiary);
            border: 1px solid var(--warning);
            border-radius: 12px;
            max-width: 90%;
        }

        .message.approval .approve-btn {
            margin-top: 12px;
            padding: 8px 16px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 13px;
            font-weight: 500;
        }

        .message.approval .approve-btn.yes {
            background: var(--success);
            color: white;
            margin-right: 8px;
        }

        .message.approval .approve-btn.no {
            background: var(--error);
            color: white;
        }

        .message .trace-id {
            margin-top: 8px;
            font-size: 11px;
            color: var(--text-secondary);
            font-family: monospace;
        }

        /* Input */
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
            padding: 12px 16px;
            border: 1px solid var(--border);
            border-radius: 10px;
            background: var(--bg-primary);
            color: var(--text-primary);
            font-size: 14px;
            outline: none;
            transition: border-color 0.2s;
        }

        .input-wrapper input:focus {
            border-color: var(--accent);
            box-shadow: 0 0 0 3px var(--accent-glow);
        }

        .input-wrapper button {
            padding: 12px 20px;
            border: none;
            border-radius: 10px;
            background: var(--accent);
            color: white;
            font-size: 14px;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
        }

        .input-wrapper button:hover {
            background: #4f46e5;
            transform: translateY(-1px);
        }

        .input-wrapper button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none;
        }

        /* Scrollbar */
        .messages::-webkit-scrollbar { width: 6px; }
        .messages::-webkit-scrollbar-track { background: transparent; }
        .messages::-webkit-scrollbar-thumb {
            background: var(--border);
            border-radius: 3px;
        }
    </style>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
</head>
<body>
    <div class="header">
        <div class="logo">T</div>
        <h1>JARVIS — THIRA Interface</h1>
        <div class="status">
            <div class="dot" id="statusDot"></div>
            <span id="statusText">Connecting...</span>
        </div>
    </div>

    <div class="messages" id="messages">
        <div class="message assistant">
            Hello. I'm JARVIS, the interface to THIRA. I can perceive your digital environment,
            make decisions, plan actions, and execute them through specialized agents.
            <br><br>
            How can I help you?
        </div>
    </div>

    <div class="input-area">
        <div class="input-wrapper">
            <input type="text" id="messageInput" placeholder="Tell THIRA what you need..."
                   autocomplete="off" autofocus>
            <button id="sendBtn" onclick="sendMessage()">Send</button>
        </div>
    </div>

    <script>
        const messagesDiv = document.getElementById('messages');
        const input = document.getElementById('messageInput');
        const sendBtn = document.getElementById('sendBtn');
        const statusDot = document.getElementById('statusDot');
        const statusText = document.getElementById('statusText');

        let ws = null;

        function connect() {
            const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${protocol}//${location.host}/ws/chat`);

            ws.onopen = () => {
                statusDot.style.background = 'var(--success)';
                statusText.textContent = 'Connected';
                sendBtn.disabled = false;
            };

            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                handleMessage(data);
            };

            ws.onclose = () => {
                statusDot.style.background = 'var(--error)';
                statusText.textContent = 'Disconnected';
                sendBtn.disabled = true;
                setTimeout(connect, 3000);
            };

            ws.onerror = () => {
                statusDot.style.background = 'var(--error)';
                statusText.textContent = 'Error';
            };
        }

        function handleMessage(data) {
            if (data.type === 'status') {
                addMessage(data.message, 'status');
            } else if (data.type === 'response') {
                const msg = addMessage(data.message, 'assistant');
                if (data.trace_id) {
                    const trace = document.createElement('div');
                    trace.className = 'trace-id';
                    trace.textContent = `Trace: ${data.trace_id}`;
                    msg.appendChild(trace);
                }
            } else if (data.type === 'approval_request') {
                addApprovalMessage(data);
            } else if (data.type === 'notification') {
                addMessage(data.message, 'status');
            } else if (data.type === 'error') {
                addMessage(data.message, 'assistant');
            }
        }

        function addMessage(text, type) {
            const div = document.createElement('div');
            div.className = `message ${type}`;
            div.textContent = text;
            messagesDiv.appendChild(div);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
            return div;
        }

        function addApprovalMessage(data) {
            const div = document.createElement('div');
            div.className = 'message approval';

            let stepsHtml = data.steps_requiring_approval.map(
                s => `<li>${s.description} (${s.agent}.${s.tool})</li>`
            ).join('');

            div.innerHTML = `
                <strong>⚠️ Approval Required</strong><br>
                ${data.message}<br>
                <ul style="margin: 8px 0; padding-left: 20px; font-size: 13px;">${stepsHtml}</ul>
                <button class="approve-btn yes" onclick="approve('${data.plan_id}', true)">✓ Approve</button>
                <button class="approve-btn no" onclick="approve('${data.plan_id}', false)">✗ Reject</button>
            `;

            messagesDiv.appendChild(div);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }

        async function approve(planId, approved) {
            const res = await fetch(`/api/approve/${planId}?approved=${approved}`, { method: 'POST' });
            const data = await res.json();
            addMessage(approved ? '✓ Approved' : '✗ Rejected', 'status');
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
