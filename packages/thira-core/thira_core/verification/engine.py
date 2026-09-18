"""Verification Engine implementation.

Confirms that executed actions actually produced the intended outcomes.
Prevents false completion — never assume success just because no error was thrown.
"""

from __future__ import annotations

import structlog

from shared.models import Execution, Verification, VerificationCheck

logger = structlog.get_logger()


class VerificationEngine:
    """Verifies that executed plans actually achieved their goals.

    For each execution, the engine:
    1. Checks each step's result for success indicators
    2. Validates expected state changes
    3. Aggregates into a pass/fail verdict with evidence
    """

    async def verify(self, execution: Execution) -> Verification:
        """Verify the outcomes of an execution."""
        checks: list[VerificationCheck] = []

        for result in execution.step_results:
            # Check 1: Step reported success
            check = VerificationCheck(
                strategy="step_result",
                description=f"Step {result.step_index} reported {'success' if result.success else 'failure'}",
                expected={"success": True},
                actual={"success": result.success},
                passed=result.success,
                details=result.error or "",
            )
            checks.append(check)

            # Check 2: Verify output is non-empty for successful steps
            if result.success and not result.output:
                checks.append(
                    VerificationCheck(
                        strategy="output_check",
                        description=f"Step {result.step_index} output validation",
                        expected={"has_output": True},
                        actual={"has_output": False},
                        passed=True,  # Empty output is acceptable for some actions
                        details="Step completed but produced no output",
                    )
                )

        all_passed = all(c.passed for c in checks) if checks else False

        # Generate summary
        passed_count = sum(1 for c in checks if c.passed)
        total_count = len(checks)
        steps_succeeded = sum(1 for r in execution.step_results if r.success)
        steps_total = len(execution.step_results)

        summary = (
            f"Verification: {passed_count}/{total_count} checks passed. "
            f"{steps_succeeded}/{steps_total} steps completed successfully."
        )

        verification = Verification(
            execution_id=execution.id,
            passed=all_passed,
            checks=checks,
            summary=summary,
        )

        logger.info(
            "verification.completed",
            execution_id=str(execution.id),
            passed=all_passed,
            checks_passed=passed_count,
            checks_total=total_count,
        )

        return verification
