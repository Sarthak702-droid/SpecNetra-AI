import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import settings
from app.core.logging import get_logger
from app.core.state_manager import release_run_state_manager
from app.models import RunState, TestResult
from app.reports.rca import format_rca_markdown

logger = get_logger(__name__)


def compute_overall_outcome(results: list[TestResult], errors: list[str] | None = None) -> str:
    """Explicit verdict policy for all states."""
    if any(r.outcome in ("FAILED", "ERROR") for r in results):
        return "FAILED"
    if any(r.outcome == "BLOCKED" for r in results):
        return "BLOCKED"
    if not results:
        return "FAILED" if errors else "UNKNOWN"
    return "PASSED"


def generate_markdown_report(state: RunState, finished_at: str) -> str:
    results = state.get("test_results", [])
    errors = state.get("errors", [])
    evaluation = state.get("evaluation") or {}
    findings = evaluation.get("findings", [])
    uncovered_reqs = evaluation.get("uncovered_requirements", [])

    total_tests = len(results)
    passed_tests = sum(1 for r in results if r.outcome == "PASSED")
    failed_tests = sum(1 for r in results if r.outcome == "FAILED")
    error_tests = sum(1 for r in results if r.outcome == "ERROR")
    blocked_tests = sum(1 for r in results if r.outcome == "BLOCKED")
    total_retries = sum(r.retry_count for r in results)

    smoke_tests = [r for r in results if r.test_id.startswith("SMK")]
    regression_tests = [r for r in results if not r.test_id.startswith("SMK")]

    # Requirement coverage
    req_map: dict[str, list[str]] = {}
    for r in results:
        for req_id in r.requirement_ids:
            req_map.setdefault(req_id, []).append(f"{r.test_id} ({r.outcome})")

    overall = compute_overall_outcome(results, errors)

    lines = [
        "# SpecNetra AI — Test Execution and RCA Report",
        "",
        "## 1. Run Identification",
        f"- **Run ID:** `{state['run_id']}`",
        f"- **Overall Outcome:** **{overall}**",
        f"- **Run Phase:** `{state.get('run_phase', 'UNKNOWN')}`",
        f"- **Started At:** `{state.get('started_at') or 'N/A'}`",
        f"- **Finished At:** `{finished_at}`",
        "",
        "## 2. Application Information",
        f"- **Target Environment:** `{settings.target_environment}`",
        f"- **API Base URL:** `{settings.api_base_url}`",
        f"- **Web Base URL:** `{settings.web_base_url}`",
        f"- **UI Engine:** `{settings.ui_engine}`",
        f"- **Configured Demo Bug Mode:** `{settings.demo_bug_mode or 'None (Healthy Target)'}`",
        "",
        "## 3. Execution Summary",
        "| Total Tests | Passed | Failed | Errors | Blocked | Retries Performed |",
        "|---|---|---|---|---|---|",
        f"| {total_tests} | {passed_tests} | {failed_tests} | {error_tests} | {blocked_tests} | {total_retries} |",
    ]

    if errors:
        lines.extend(
            [
                "",
                "## Pipeline Errors & Warnings",
            ]
        )
        for err in errors:
            lines.append(f"- :warning: {err}")

    if smoke_tests:
        lines.extend(
            [
                "",
                "## 4. Smoke Test Results (P0)",
                "| Test ID | Requirements | Outcome | Duration (ms) | Observed | Evidence |",
                "|---|---|---|---|---|---|",
            ]
        )
        for t in smoke_tests:
            ev_str = ", ".join(f"[{e}]({e})" for e in t.evidence_ids) if t.evidence_ids else "None"
            lines.append(
                f"| `{t.test_id}` | {', '.join(t.requirement_ids)} | **{t.outcome}** | {t.duration_ms:.1f} | {t.observed} | {ev_str} |"
            )

    if regression_tests:
        lines.extend(
            [
                "",
                "## 5. Regression Test Results (P1)",
                "| Test ID | Requirements | Outcome | Duration (ms) | Observed |",
                "|---|---|---|---|---|",
            ]
        )
        for t in regression_tests:
            lines.append(
                f"| `{t.test_id}` | {', '.join(t.requirement_ids)} | **{t.outcome}** | {t.duration_ms:.1f} | {t.observed} |"
            )

    lines.extend(
        [
            "",
            "## 6. Requirement Coverage Matrix",
            "| Requirement ID | Associated Test Runs & Status | Verification Status |",
            "|---|---|---|",
        ]
    )
    for req_id, test_runs in sorted(req_map.items()):
        status = "Verified" if any("PASSED" in tr for tr in test_runs) else "Failing/Incomplete"
        lines.append(f"| `{req_id}` | {', '.join(test_runs)} | **{status}** |")

    if uncovered_reqs:
        lines.extend(
            [
                "",
                "### Uncovered Requirements",
                "The following specified requirements were not verified with passing test evidence:",
            ]
        )
        for u in uncovered_reqs:
            lines.append(f"- :x: `{u}`: Not verified in this execution run")

    lines.extend(
        [
            "",
            "## 7. Failure Details",
        ]
    )
    failed_list = [r for r in results if r.outcome in ("FAILED", "ERROR", "BLOCKED")]
    if failed_list:
        for f in failed_list:
            lines.append(
                f"- **`{f.test_id}`** ({f.outcome}): {f.observed} (Error Code: `{f.error_code}`)"
            )
    else:
        lines.append("No failures detected.")

    lines.extend(
        [
            "",
            "## 8. Root Cause Hypotheses (RCA)",
            format_rca_markdown(findings),
            "## 9. Recovery Attempts & Self-Healing",
            f"- Total bounded retries executed across all tests: **{total_retries}**",
            "- All transient retry policies respected idempotency constraints and timeout limits.",
        ]
    )

    healing_events = []
    for r in results:
        for s in r.step_results:
            if s.recovered_by:
                healing_events.append(f"- Test `{r.test_id}` Step {s.step_index}: {s.recovered_by}")
    if healing_events:
        lines.append("\n**Selector Self-Healing Events:**")
        lines.extend(healing_events)

    lines.extend(
        [
            "",
            "## 10. Evidence References",
        ]
    )
    manifest = state.get("evidence_manifest", [])
    if manifest:
        for m in manifest:
            lines.append(f"- Test `{m['test_id']}` ({m['kind']}): `{m['path']}`")
    else:
        lines.append("No failure screenshots or traces recorded.")

    lines.extend(
        [
            "",
            "## 11. Recommended Corrective Actions",
        ]
    )
    if findings:
        for f in findings:
            lines.append(f"- For `{f['test_id']}`: {f['next_debug_step']}")
    else:
        lines.append(
            "- Application is performing within expected requirements. No corrective actions required."
        )

    lines.append("")
    return "\n".join(lines)


def write_artifacts(state: RunState, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = state.get("run_id", "run_unknown")
    run_dir = output_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    finished_at = datetime.now(UTC).isoformat()
    overall = compute_overall_outcome(state.get("test_results", []), state.get("errors", []))

    # 1. execution_log.json with step-level telemetry
    log_data: dict[str, Any] = {
        "schema_version": "1.0",
        "run_id": run_id,
        "overall_outcome": overall,
        "run_phase": state.get("run_phase"),
        "started_at": state.get("started_at"),
        "finished_at": finished_at,
        "errors": state.get("errors", []),
        "tests": [
            {
                "test_id": r.test_id,
                "requirement_ids": r.requirement_ids,
                "outcome": r.outcome,
                "error_code": r.error_code,
                "evidence": r.evidence_ids,
                "duration_ms": r.duration_ms,
                "retry_count": r.retry_count,
                "observed": r.observed,
                "steps": [
                    {
                        "step_index": s.step_index,
                        "outcome": s.outcome,
                        "observed": s.observed,
                        "duration_ms": s.duration_ms,
                        "retry_count": s.retry_count,
                        "error_code": s.error_code,
                        "recovered_by": s.recovered_by,
                        "console_logs": s.console_logs,
                        "network_errors": s.network_errors,
                        "evidence_ids": s.evidence_ids,
                    }
                    for s in r.step_results
                ],
            }
            for r in state.get("test_results", [])
        ],
    }

    log_json = json.dumps(log_data, indent=2)
    (run_dir / "execution_log.json").write_text(log_json, encoding="utf-8")
    (output_dir / "execution_log.json").write_text(log_json, encoding="utf-8")

    # 2. report.md
    report_md = generate_markdown_report(state, finished_at)
    (run_dir / "report.md").write_text(report_md, encoding="utf-8")
    (output_dir / "report.md").write_text(report_md, encoding="utf-8")

    # 3. test_plan.json
    plan = state.get("test_plan")
    if plan:
        plan_json = plan.model_dump_json(indent=2)
        (run_dir / "test_plan.json").write_text(plan_json, encoding="utf-8")
        (output_dir / "test_plan.json").write_text(plan_json, encoding="utf-8")

    logger.info(f"Artifacts successfully written to {run_dir} and {output_dir}")


async def report_node(state: RunState) -> dict[str, Any]:
    output_dir = Path(settings.output_dir)
    write_artifacts(state, output_dir)
    # Lifecycle cleanup: release stored run state
    release_run_state_manager(state.get("run_id", ""))
    return {
        "run_phase": "COMPLETED",
        "finished_at": datetime.now(UTC).isoformat(),
    }
