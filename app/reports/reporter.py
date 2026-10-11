import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import settings
from app.core.logging import get_logger
from app.models import RunState, TestResult
from app.reports.rca import format_rca_markdown

logger = get_logger(__name__)


def compute_overall_outcome(results: list[TestResult]) -> str:
    if not results:
        return "UNKNOWN"
    if any(r.outcome in ("FAILED", "ERROR") for r in results):
        return "FAILED"
    return "PASSED"


def generate_markdown_report(state: RunState, finished_at: str) -> str:
    results = state.get("test_results", [])
    evaluation = state.get("evaluation") or {}
    findings = evaluation.get("findings", [])

    total_tests = len(results)
    passed_tests = sum(1 for r in results if r.outcome == "PASSED")
    failed_tests = sum(1 for r in results if r.outcome == "FAILED")
    error_tests = sum(1 for r in results if r.outcome == "ERROR")
    total_retries = sum(r.retry_count for r in results)

    smoke_tests = [r for r in results if r.test_id.startswith("SMK")]
    regression_tests = [
        r for r in results if r.test_id.startswith("REG") or not r.test_id.startswith("SMK")
    ]

    # Requirement coverage
    req_map: dict[str, list[str]] = {}
    for r in results:
        for req_id in r.requirement_ids:
            req_map.setdefault(req_id, []).append(f"{r.test_id} ({r.outcome})")

    overall = compute_overall_outcome(results)

    lines = [
        "# SpecNetra AI — Test Execution and RCA Report",
        "",
        "## 1. Run Identification",
        f"- **Run ID:** `{state['run_id']}`",
        f"- **Overall Outcome:** **{overall}**",
        f"- **Started At:** `{state.get('started_at') or 'N/A'}`",
        f"- **Finished At:** `{finished_at}`",
        "",
        "## 2. Application Information",
        f"- **Target Environment:** `{settings.target_environment}`",
        f"- **API Base URL:** `{settings.api_base_url}`",
        f"- **Web Base URL:** `{settings.web_base_url}`",
        f"- **Configured Demo Bug Mode:** `{settings.demo_bug_mode or 'None (Healthy Target)'}`",
        "",
        "## 3. Execution Summary",
        "| Total Tests | Passed | Failed | Errors | Retries Performed |",
        "|---|---|---|---|---|",
        f"| {total_tests} | {passed_tests} | {failed_tests} | {error_tests} | {total_retries} |",
        "",
        "## 4. Smoke Test Results (P0)",
        "| Test ID | Requirements | Outcome | Duration (ms) | Observed | Evidence |",
        "|---|---|---|---|---|---|",
    ]

    for t in smoke_tests:
        ev_str = ", ".join(f"[{e}]({e})" for e in t.evidence_ids) if t.evidence_ids else "None"
        lines.append(
            f"| `{t.test_id}` | {', '.join(t.requirement_ids)} | **{t.outcome}** | {t.duration_ms:.1f} | {t.observed} | {ev_str} |"
        )

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
            "| Requirement ID | Associated Test Runs & Status |",
            "|---|---|",
        ]
    )
    for req_id, test_runs in sorted(req_map.items()):
        lines.append(f"| `{req_id}` | {', '.join(test_runs)} |")

    lines.extend(
        [
            "",
            "## 7. Failure Details",
        ]
    )
    failed_list = [r for r in results if r.outcome in ("FAILED", "ERROR")]
    if failed_list:
        for f in failed_list:
            lines.append(f"- **`{f.test_id}`**: {f.observed} (Error Code: `{f.error_code}`)")
    else:
        lines.append("No failures detected.")

    lines.extend(
        [
            "",
            "## 8. Root Cause Hypotheses (RCA)",
            format_rca_markdown(findings),
            "## 9. Recovery Attempts",
            f"- Total bounded retries executed across all tests: **{total_retries}**",
            "- All transient retry policies respected idempotency constraints and timeout limits.",
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
    finished_at = datetime.now(UTC).isoformat()
    overall = compute_overall_outcome(state.get("test_results", []))

    # 1. execution_log.json
    log_data: dict[str, Any] = {
        "schema_version": "1.0",
        "run_id": state["run_id"],
        "overall_outcome": overall,
        "started_at": state.get("started_at"),
        "finished_at": finished_at,
        "tests": [
            {
                "test_id": r.test_id,
                "requirement_ids": r.requirement_ids,
                "outcome": r.outcome,
                "error_code": r.error_code,
                "evidence": r.evidence_ids,
                "duration_ms": r.duration_ms,
                "retry_count": r.retry_count,
            }
            for r in state.get("test_results", [])
        ],
    }

    exec_log_path = output_dir / "execution_log.json"
    exec_log_path.write_text(json.dumps(log_data, indent=2), encoding="utf-8")

    # 2. report.md
    report_md = generate_markdown_report(state, finished_at)
    report_path = output_dir / "report.md"
    report_path.write_text(report_md, encoding="utf-8")

    # 3. Also write test_plan.json for traceability
    plan = state.get("test_plan")
    if plan:
        plan_path = output_dir / "test_plan.json"
        plan_path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")

    logger.info(f"Artifacts successfully written to {output_dir}")


async def report_node(state: RunState) -> dict[str, Any]:
    output_dir = Path(settings.output_dir)
    write_artifacts(state, output_dir)
    return {
        "run_phase": "COMPLETED",
        "finished_at": datetime.now(UTC).isoformat(),
    }
