"""Enumerations used across the THIRA platform."""

from enum import Enum


class EventSource(str, Enum):
    """Sources of events that THIRA can perceive."""

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
    """Types of events THIRA can process."""

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
    """Priority levels for events and decisions."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class DecisionAction(str, Enum):
    """What THIRA decides to do about an event."""

    ACT = "act"
    IGNORE = "ignore"
    DEFER = "defer"
    ESCALATE = "escalate"
    MONITOR = "monitor"


class AutonomyLevel(int, Enum):
    """Autonomy levels for agent actions (L0–L5)."""

    L0_OBSERVE = 0  # Read-only, no external actions
    L1_RECOMMEND = 1  # Suggest actions, no execution
    L2_PREPARE = 2  # Draft actions, don't send
    L3_EXECUTE_APPROVED = 3  # Execute after explicit user approval
    L4_EXECUTE_AUTO = 4  # Execute without asking (reversible)
    L5_AUTONOMOUS = 5  # Autonomous multi-step execution


class PlanStatus(str, Enum):
    """Status of a plan."""

    PENDING = "pending"
    APPROVED = "approved"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExecutionStatus(str, Enum):
    """Status of an execution."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


class StepStatus(str, Enum):
    """Status of an individual execution step."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class AgentState(str, Enum):
    """Lifecycle states for agents."""

    REGISTERED = "registered"
    INITIALIZING = "initializing"
    READY = "ready"
    EXECUTING = "executing"
    RECOVERING = "recovering"
    FAILED = "failed"
    STOPPED = "stopped"


class PolicyVerdict(str, Enum):
    """Result of a policy check."""

    ALLOWED = "allowed"
    REQUIRES_APPROVAL = "requires_approval"
    BLOCKED = "blocked"


class RiskLevel(str, Enum):
    """Risk levels for tool annotations."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RecoveryAction(str, Enum):
    """What to do when a step fails."""

    RETRY = "retry"
    SKIP = "skip"
    REPLAN = "replan"
    ABORT = "abort"
    ESCALATE = "escalate"
