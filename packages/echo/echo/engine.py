"""ECHO Engine implementation.

Records experiences and retrieves similar past experiences via semantic search.
The fundamental data structure: Context → Decision → Action → Outcome → Learning.
"""

from __future__ import annotations

import structlog
from sqlalchemy import insert, select, text

from shared.db.models import ExperienceModel
from shared.events import EnrichedEvent, ThiraEvent
from shared.llm.provider import LLMMessage, LLMProvider
from shared.models import (
    Decision,
    Execution,
    Experience,
    Learning,
    Plan,
    Verification,
)

logger = structlog.get_logger()


class EchoEngine:
    """Experience & Learning Engine — the memory that learns.

    Unlike simple conversation memory, ECHO stores causal chains:
    what happened → what was decided → what was done → what resulted → what was learned.

    This enables THIRA to:
    - Recall how similar situations were handled before
    - Avoid repeating mistakes
    - Improve decision-making over time
    - Provide explanations grounded in experience
    """

    def __init__(self, db_session_factory, llm: LLMProvider):
        self._session_factory = db_session_factory
        self._llm = llm

    async def record(
        self,
        *,
        event: ThiraEvent,
        enriched: EnrichedEvent,
        decision: Decision,
        plan: Plan,
        execution: Execution,
        verification: Verification,
    ) -> Experience:
        """Record a complete experience from one THIRA loop iteration.

        Generates summaries, extracts learnings, creates embedding,
        and stores everything in the database.
        """
        # Generate summaries
        context_summary = enriched.interpretation or event.content[:200]
        decision_summary = f"Action: {decision.action.value}. {decision.reasoning}"
        action_summary = (
            f"Executed {len(execution.step_results)} steps. {execution.steps_completed} succeeded."
        )
        outcome_summary = verification.summary
        success = verification.passed

        # Extract learnings via LLM
        learnings = await self._extract_learnings(
            context_summary, decision_summary, action_summary, outcome_summary, success
        )

        # Create experience
        experience = Experience(
            event_id=event.id,
            decision_id=decision.id,
            plan_id=plan.id,
            execution_id=execution.id,
            context_summary=context_summary,
            decision_summary=decision_summary,
            action_summary=action_summary,
            outcome_summary=outcome_summary,
            success=success,
            learnings=learnings,
        )

        # Generate embedding for semantic retrieval
        embedding_text = f"{context_summary} {decision_summary} {outcome_summary}"
        embedding = await self._llm.embed(embedding_text)

        # Persist to database
        async with self._session_factory() as session:
            await session.execute(
                insert(ExperienceModel).values(
                    id=experience.id,
                    event_id=event.id,
                    decision_id=decision.id,
                    plan_id=plan.id,
                    execution_id=execution.id,
                    context_summary=context_summary,
                    decision_summary=decision_summary,
                    action_summary=action_summary,
                    outcome_summary=outcome_summary,
                    success=success,
                    learnings=[l.model_dump() for l in learnings],
                    embedding=embedding,
                )
            )
            await session.commit()

        logger.info(
            "echo.recorded",
            experience_id=str(experience.id),
            success=success,
            learnings=len(learnings),
        )

        return experience

    async def retrieve_similar(self, query: str, k: int = 5) -> list[Experience]:
        """Retrieve the k most similar past experiences using semantic search.

        Uses pgvector cosine similarity on experience embeddings, with an
        in-memory vector calculation fallback for non-Postgres environments.
        """
        # Generate query embedding
        query_embedding = await self._llm.embed(query)

        experiences = []
        try:
            async with self._session_factory() as session:
                # pgvector cosine distance query
                result = await session.execute(
                    text("""
                        SELECT id, event_id, decision_id, plan_id, execution_id,
                               context_summary, decision_summary, action_summary,
                               outcome_summary, success, learnings,
                               embedding <=> :query_embedding AS distance
                        FROM experiences
                        WHERE embedding IS NOT NULL
                        ORDER BY embedding <=> :query_embedding
                        LIMIT :k
                    """),
                    {"query_embedding": str(query_embedding), "k": k},
                )
                rows = result.fetchall()

            for row in rows:
                learnings_data = row.learnings if row.learnings else []
                experiences.append(
                    Experience(
                        id=row.id,
                        event_id=row.event_id,
                        decision_id=row.decision_id,
                        plan_id=row.plan_id,
                        execution_id=row.execution_id,
                        context_summary=row.context_summary,
                        decision_summary=row.decision_summary,
                        action_summary=row.action_summary,
                        outcome_summary=row.outcome_summary,
                        success=row.success,
                        learnings=[Learning(**l) for l in learnings_data],
                    )
                )
        except Exception:
            # Fallback for non-pgvector environments (e.g. SQLite in integration tests)
            async with self._session_factory() as session:
                result = await session.execute(select(ExperienceModel))
                all_models = result.scalars().all()

            def _cosine_sim(v1: list[float], v2: list[float] | None) -> float:
                if not v1 or not v2:
                    return 0.0
                dot = sum(a * b for a, b in zip(v1, v2))
                norm1 = sum(a * a for a in v1) ** 0.5
                norm2 = sum(b * b for b in v2) ** 0.5
                if norm1 == 0 or norm2 == 0:
                    return 0.0
                return dot / (norm1 * norm2)

            scored = sorted(
                all_models,
                key=lambda m: _cosine_sim(
                    query_embedding, list(m.embedding) if m.embedding is not None else None
                ),
                reverse=True,
            )[:k]

            for m in scored:
                learnings_data = m.learnings if m.learnings else []
                experiences.append(
                    Experience(
                        id=m.id,
                        event_id=m.event_id,
                        decision_id=m.decision_id,
                        plan_id=m.plan_id,
                        execution_id=m.execution_id,
                        context_summary=m.context_summary,
                        decision_summary=m.decision_summary,
                        action_summary=m.action_summary,
                        outcome_summary=m.outcome_summary,
                        success=m.success,
                        learnings=[Learning(**l) for l in learnings_data],
                    )
                )

        logger.debug("echo.retrieved", query=query[:50], results=len(experiences))
        return experiences

    async def _extract_learnings(
        self,
        context: str,
        decision: str,
        action: str,
        outcome: str,
        success: bool,
    ) -> list[Learning]:
        """Use LLM to extract learnings from an experience."""
        response = await self._llm.complete(
            messages=[
                LLMMessage(
                    role="system",
                    content=(
                        "You are a learning extraction engine. Given an experience "
                        "(context, decision, action, outcome), extract 1-3 actionable learnings. "
                        "Return a JSON array of objects with fields: "
                        "'insight' (what was observed), 'pattern' (the generalizable pattern), "
                        "'recommendation' (what to do in future similar situations), "
                        "'confidence' (0.0-1.0). Return ONLY the JSON array."
                    ),
                ),
                LLMMessage(
                    role="user",
                    content=(
                        f"Context: {context}\n"
                        f"Decision: {decision}\n"
                        f"Action: {action}\n"
                        f"Outcome: {outcome}\n"
                        f"Success: {success}"
                    ),
                ),
            ],
            json_mode=True,
            temperature=0.3,
            purpose="learning_extraction",
        )

        try:
            import json

            raw = json.loads(response.content)
            data = raw if isinstance(raw, list) else raw.get("learnings", [])
            return [
                Learning(
                    insight=l.get("insight", ""),
                    pattern=l.get("pattern", ""),
                    recommendation=l.get("recommendation", ""),
                    confidence=l.get("confidence", 0.8),
                )
                for l in data
            ]
        except Exception as e:
            logger.warning("echo.learning_extraction_failed", error=str(e))
            return []
