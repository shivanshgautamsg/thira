"""Decision Engine implementation.

Multi-factor decision making: urgency, importance, opportunity, effort,
confidence, risk, reversibility, dependency.
"""

from __future__ import annotations

import json

import structlog

from shared.enums import DecisionAction
from shared.events import EnrichedEvent
from shared.llm.provider import LLMMessage, LLMProvider
from shared.models import Decision, DecisionScores

logger = structlog.get_logger()


class DecisionEngine:
    """Determines what matters and what should happen.

    For every enriched event, the Decision Engine evaluates 8 factors
    and produces a Decision: ACT, IGNORE, DEFER, ESCALATE, or MONITOR.

    This is NOT just priority ranking — it's decision intelligence.
    """

    def __init__(self, llm: LLMProvider):
        self._llm = llm

    async def evaluate(self, event: EnrichedEvent, world_model: object) -> Decision:
        """Evaluate an enriched event and decide what to do.

        Uses LLM-based multi-factor scoring to determine:
        - Whether to act, ignore, defer, escalate, or monitor
        - The urgency, importance, and risk profile
        - The reasoning behind the decision
        """
        response = await self._llm.complete(
            messages=[
                LLMMessage(
                    role="system",
                    content=DECISION_SYSTEM_PROMPT,
                ),
                LLMMessage(
                    role="user",
                    content=self._build_decision_prompt(event),
                ),
            ],
            json_mode=True,
            temperature=0.2,
            purpose="decision_scoring",
        )

        try:
            result = json.loads(response.content)
            scores = DecisionScores(
                urgency=result.get("urgency", 0.5),
                importance=result.get("importance", 0.5),
                opportunity=result.get("opportunity", 0.5),
                effort=result.get("effort", 0.5),
                confidence=result.get("confidence", 0.5),
                risk=result.get("risk", 0.5),
                reversibility=result.get("reversibility", 0.5),
                dependency=result.get("dependency", 0.0),
            )

            action_str = result.get("action", "act").lower()
            action = (
                DecisionAction(action_str)
                if action_str in DecisionAction.__members__.values()
                else DecisionAction.ACT
            )

            decision = Decision(
                event_id=event.event.id,
                action=action,
                scores=scores,
                reasoning=result.get("reasoning", ""),
            )

            logger.info(
                "decision.evaluated",
                event_id=str(event.event.id),
                action=decision.action.value,
                urgency=scores.urgency,
                importance=scores.importance,
                reasoning=decision.reasoning[:100],
            )

            return decision

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning("decision.parse_failed", error=str(e))
            # Default: act on the event
            return Decision(
                event_id=event.event.id,
                action=DecisionAction.ACT,
                scores=DecisionScores(),
                reasoning=f"Default decision (parsing failed): {e}",
            )

    def _build_decision_prompt(self, event: EnrichedEvent) -> str:
        """Build the decision prompt from the enriched event."""
        entities = [e.entity.name for e in event.resolved_entities]
        context_items = [c.content for c in event.related_context[:5]]
        echo_items = [
            f"Past: {e.context_summary} → {e.outcome_summary} ({'success' if e.success else 'failure'})"
            for e in event.echo_matches[:3]
        ]

        return f"""Evaluate this event and decide what action to take.

EVENT:
Source: {event.event.source.value}
Type: {event.event.type.value}
Content: {event.event.content}
Actor: {event.event.actor or "unknown"}
Current Priority: {event.event.priority.value}

ENTITIES: {", ".join(entities) if entities else "none extracted"}

INTERPRETATION: {event.interpretation}

RELATED CONTEXT:
{chr(10).join(context_items) if context_items else "No additional context available."}

PAST EXPERIENCES:
{chr(10).join(echo_items) if echo_items else "No similar past experiences found."}
"""


DECISION_SYSTEM_PROMPT = """You are a decision intelligence engine for an autonomous agent platform called THIRA.

Given an event with context, you must evaluate it across 8 factors and decide what action to take.

Return a JSON object with these fields:

{
    "action": "act" | "ignore" | "defer" | "escalate" | "monitor",
    "urgency": 0.0-1.0,        // How soon does this matter?
    "importance": 0.0-1.0,     // What happens if it isn't handled?
    "opportunity": 0.0-1.0,    // What value could acting create?
    "effort": 0.0-1.0,         // How expensive is the action? (1.0 = very expensive)
    "confidence": 0.0-1.0,     // How certain are you about this interpretation?
    "risk": 0.0-1.0,           // What could go wrong? (1.0 = very risky)
    "reversibility": 0.0-1.0,  // Can the action be undone? (1.0 = fully reversible)
    "dependency": 0.0-1.0,     // Are other things blocked by this?
    "reasoning": "2-3 sentence explanation of the decision"
}

Decision guidelines:
- "act": The event requires action and we should proceed
- "ignore": The event is informational only, no action needed
- "defer": Important but can wait — schedule for later
- "escalate": Too risky or uncertain — ask the user
- "monitor": Watch for developments before acting

For user commands/requests, almost always choose "act" unless the request is unclear.
For automated events, use full multi-factor analysis."""
