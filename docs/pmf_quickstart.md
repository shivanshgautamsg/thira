# THIRA MVP — Quickstart & Pilot Guide

Welcome to **THIRA** (Agentic Intelligence & Autonomous Execution Platform with JARVIS Human Interface and ECHO Memory).

THIRA continuously perceives your digital environment (email, schedule, messages), builds contextual understanding, decides what matters, plans actions, safely executes through specialized tools, verifies outcomes, and learns from experience.

---

## ⚡ 1-Minute Quickstart (Instant Local Demo)

You can run THIRA locally with zero cloud configuration:

```bash
# 1. Install dependencies
uv sync

# 2. Run the interactive live demo scenario
uv run python scripts/demo.py

# 3. Start the JARVIS web interface
uv run python main.py
```

Open **[http://localhost:8000](http://localhost:8000)** in your browser.

---

## 🖥️ The JARVIS Interface

The JARVIS interface is designed for high-agency human-in-the-loop interaction:

- **Live Cognitive Trace Panel**: As events arrive, watch THIRA's 8-factor decision radar (Urgency, Importance, Risk) and plan DAG execute in real time.
- **Human Authorization Cards**: Sensitive or external-facing operations (such as sending an email or updating client calendar events) halt with an interactive card. Click **"Authorize & Execute"** or **"Decline"**.
- **1-Click Demo Triggers**:
  - `🌅 Morning Briefing`: Summarizes upcoming calendar meetings and urgent unread items.
  - `✉️ Inbound RFP Email`: Simulates a high-priority client email, extracts entities into the World Model, checks the schedule, and prepares a draft reply.
  - `📅 Check Schedule`: Queries calendar events and flags upcoming commitments.

---

## 🔌 Connecting Live Google Workspace (Gmail & Calendar)

By default, THIRA operates in zero-credential mock mode for safe local evaluation. To connect your live personal or enterprise Google account:

### Step 1: Create Google Cloud Credentials
1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Enable the **Gmail API** and **Google Calendar API**.
3. Under **APIs & Services > Credentials**, create an **OAuth 2.0 Client ID** (Desktop Application).
4. Download the credentials or copy your `Client ID` and `Client Secret`.

### Step 2: Configure Environment Variables
Copy `.env.example` to `.env` and configure:

```env
# OpenAI LLM
OPENAI_API_KEY=sk-...

# Google Workspace Integration
GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-client-secret
GOOGLE_REFRESH_TOKEN=your-refresh-token
CALENDAR_ID=primary
```

> [!TIP]
> When `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REFRESH_TOKEN` are set, THIRA automatically switches from in-memory mocks to live Google APIs. If absent, it gracefully falls back to mock mode.

---

## 🏛️ Autonomous Platform Architecture

```text
                  INBOUND STREAMS
       (Gmail, Calendar, Filesystem, Terminal)
                         │
                         ▼
                   [ PERCEIVE ]
                         │
                         ▼
                  [ UNDERSTAND ]
             (Entity Resolution & World Model)
                         │
                         ▼
                    [ DECIDE ]
             (8-Factor Urgency & Importance)
                         │
                         ▼
                     [ PLAN ]
                  (Execution DAG)
                         │
                         ▼
                   [ AUTHORIZE ]
             (L0–L5 Autonomy & Safety Policy)
                    ╱         ╲
           Safe Steps         Requires Approval
               │                      │
               │               [ JARVIS MODAL ]
               │                      │
               ▼                      ▼
           [ ACT: Specialized Agents (Gmail, Calendar, Terminal, Filesystem) ]
                         │
                         ▼
                    [ VERIFY ]
             (Deterministic Outcome Verification)
                         │
                         ▼
                    [ LEARN ]
       (ECHO Causal Chain & Vector Similarity Memory)
```

---

## 🧪 Running Automated Tests

THIRA comes with 100% passing test coverage across unit engines and full integration loops:

```bash
uv run pytest
```

---

## 💬 Feedback & Design Partner Onboarding

To report issues, request new agent capabilities, or discuss enterprise deployments, reach out to the project maintainer:
- GitHub: [github.com/shivanshgautamsg/thira](https://github.com/shivanshgautamsg/thira)
