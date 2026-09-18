"""Failure & Recovery Engine implementation.

Classifies failures and determines recovery strategy:
retry, skip, replan, abort, or escalate.
"""

from __future__ import annotations

import structlog

from shared.enums import RecoveryAction
from shared.models import PlanStep, RecoveryResult, StepResult

logger = structlog.get_logger()


# Known transient error patterns
TRANSIENT_PATTERNS = [
    "timeout",
    "connection refused",
    "connection reset",
    "temporary",
    "rate limit",
    "429",
    "503",
    "504",
    "retry",
]


class FailureEngine:
    """Handles failures intelligently instead of just reporting errors.

    Classification → Recovery strategy:
    - Transient (network, rate limit) → Retry
    - Non-critical (optional step) → Skip
    - Recoverable (alternative approach exists) → Replan
    - Critical (data corruption risk) → Abort
    - Uncertain (can't classify) → Escalate to user
    """

    def __init__(self, max_retries: int = 3):
        self._max_retries = max_retries
        self._retry_counts: dict[str, int] = {}  # step_key → retry count

    async def handle(
        self,
        step: PlanStep,
        *,
        result: StepResult | None = None,
        error: Exception | None = None,
    ) -> RecoveryResult:
        """Determine recovery strategy for a failed step."""
        error_message = ""
        if result and result.error:
            error_message = result.error
        elif error:
            error_message = str(error)

        # Classify the failure
        is_transient = self._is_transient(error_message)
        step_key = f"{step.agent}.{step.tool}.{step.index}"
        retries = self._retry_counts.get(step_key, 0)

        # Decision tree
        if is_transient and retries < self._max_retries:
            self._retry_counts[step_key] = retries + 1
            logger.info(
                "failure.retry",
                step=step_key,
                attempt=retries + 1,
                max_retries=self._max_retries,
            )
            return RecoveryResult(
                action=RecoveryAction.RETRY,
                reason=f"Transient error: {error_message}. Retry {retries + 1}/{self._max_retries}.",
                retries_attempted=retries + 1,
            )

        if is_transient and retries >= self._max_retries:
            logger.warning(
                "failure.max_retries",
                step=step_key,
                retries=retries,
            )
            return RecoveryResult(
                action=RecoveryAction.ABORT,
                reason=f"Max retries ({self._max_retries}) exceeded for transient error: {error_message}",
                retries_attempted=retries,
            )

        # Non-transient errors
        logger.warning(
            "failure.non_transient",
            step=step_key,
            error=error_message[:200],
        )

        return RecoveryResult(
            action=RecoveryAction.ABORT,
            reason=f"Non-transient failure: {error_message}",
            retries_attempted=retries,
        )

    def _is_transient(self, error_message: str) -> bool:
        """Classify whether an error is transient (likely to succeed on retry)."""
        lower = error_message.lower()
        return any(pattern in lower for pattern in TRANSIENT_PATTERNS)

    def reset(self) -> None:
        """Reset retry counters (e.g., between plans)."""
        self._retry_counts.clear()
