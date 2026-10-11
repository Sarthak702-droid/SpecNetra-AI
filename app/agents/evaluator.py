import json
from typing import Any

from app.config import settings
from app.core.logging import get_logger
from app.core.security import sanitize_for_prompt
from app.models import RCAFinding, RunState, TestResult

logger = get_logger(__name__)


def deterministic_rca(failed_results: list[TestResult]) -> list[RCAFinding]:
    """
    Deterministic rule-based Root Cause Analysis when offline or as primary/fallback.
    """
    findings: list[RCAFinding] = []
    for r in failed_results:
        observed = r.observed
        test_id = r.test_id
        req_ids = r.requirement_ids

        if "not visible" in observed.lower() or "not found" in observed.lower():
            findings.append(
                RCAFinding(
                    test_id=test_id,
                    requirement_ids=req_ids,
                    observed_evidence=f"{observed}. Evidence captured: {r.evidence_ids}",
                    hypothesis="Frontend data-loading, rendering synchronization, or backend record availability mismatch",
                    confidence="high",
                    next_debug_step="Inspect the appointment retrieval request, frontend state updates, and browser console output",
                )
            )
        elif "status code mismatch" in observed.lower() or "401" in observed or "422" in observed:
            findings.append(
                RCAFinding(
                    test_id=test_id,
                    requirement_ids=req_ids,
                    observed_evidence=f"{observed}",
                    hypothesis="API contract violation or input validation handling discrepancy",
                    confidence="high",
                    next_debug_step="Verify request payload schema, authorization headers, and backend route validation rules",
                )
            )
        else:
            findings.append(
                RCAFinding(
                    test_id=test_id,
                    requirement_ids=req_ids,
                    observed_evidence=f"{observed}",
                    hypothesis="Execution failure during test step execution",
                    confidence="medium",
                    next_debug_step="Inspect execution logs and network communication for service errors",
                )
            )
    return findings


async def evaluate_node(state: RunState) -> dict[str, Any]:
    all_results = state.get("test_results", [])
    failed_results = [r for r in all_results if r.outcome in ("FAILED", "ERROR")]

    if not failed_results:
        return {
            "evaluation": {
                "overall_verdict": "PASSED",
                "summary": "All tests passed successfully against requirement specifications.",
                "findings": [],
            },
            "run_phase": "EVALUATING",
        }

    findings: list[RCAFinding] = []

    # Attempt AI-based RCA if configured
    if settings.plan_mode != "fixture":
        try:
            from pydantic_ai import Agent

            evaluator_agent = Agent(
                f"{settings.llm_provider}:{settings.llm_model}",
                output_type=list[RCAFinding],
                system_prompt="""
You are an expert Root Cause Analysis (RCA) evaluator for SpecNetra AI.
Analyze the test failure evidence and propose evidence-grounded hypotheses.
Rules:
1. Distinguish observed evidence from hypothetical explanation.
2. Provide concrete next debug steps.
3. Assign confidence: high, medium, or low.
4. Do NOT disclose or reference secrets.
""",
            )

            prompt_data = sanitize_for_prompt(
                {
                    "failed_tests": [
                        {
                            "test_id": r.test_id,
                            "requirement_ids": r.requirement_ids,
                            "observed": r.observed,
                            "evidence_ids": r.evidence_ids,
                            "error_code": r.error_code,
                        }
                        for r in failed_results
                    ]
                }
            )

            res = await evaluator_agent.run(json.dumps(prompt_data))
            findings = res.output
        except Exception as e:
            logger.warning(f"AI RCA evaluation failed ({e}); falling back to deterministic RCA")
            findings = deterministic_rca(failed_results)
    else:
        findings = deterministic_rca(failed_results)

    return {
        "evaluation": {
            "overall_verdict": "FAILED",
            "summary": f"{len(failed_results)} tests failed out of {len(all_results)} total tests.",
            "findings": [f.model_dump() for f in findings],
        },
        "run_phase": "EVALUATING",
    }
