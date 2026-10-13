import argparse
import asyncio
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.config import settings
from app.core.logging import configure_logging, get_logger
from app.graph import graph
from app.models import AuthState, ResourceRefs, RunState

logger = get_logger("specnetra.main")


def parse_args():
    parser = argparse.ArgumentParser(description="SpecNetra AI Autonomous Testing Framework")
    parser.add_argument(
        "--requirements", default="inputs/requirements.md", help="Path to requirements.md"
    )
    parser.add_argument("--openapi", default="inputs/openapi.json", help="Path to openapi.json")
    parser.add_argument(
        "--scenarios", default="inputs/scenarios.json", help="Path to scenarios.json"
    )
    parser.add_argument("--api-url", default=None, help="Base URL for target API")
    parser.add_argument("--web-url", default=None, help="Base URL for target Web frontend")
    return parser.parse_args()


async def main_async():
    configure_logging()
    args = parse_args()

    from urllib.parse import urlparse

    if args.api_url:
        settings.api_base_url = args.api_url
        api_host = urlparse(args.api_url).hostname
        if api_host:
            if isinstance(settings.allowed_target_hosts, list):
                if api_host not in settings.allowed_target_hosts:
                    settings.allowed_target_hosts.append(api_host)
            else:
                settings.allowed_target_hosts = [settings.allowed_target_hosts, api_host]

    if args.web_url:
        settings.web_base_url = args.web_url
        web_host = urlparse(args.web_url).hostname
        if web_host:
            if isinstance(settings.allowed_target_hosts, list):
                if web_host not in settings.allowed_target_hosts:
                    settings.allowed_target_hosts.append(web_host)
            else:
                settings.allowed_target_hosts = [settings.allowed_target_hosts, web_host]

    run_id = f"run_{uuid.uuid4().hex[:8]}"
    started_at = datetime.now(UTC).isoformat()

    print("[INFO] SpecNetra AI initialized")
    print(f"[INFO] Run ID: {run_id}")
    print(f"[INFO] Target API: {settings.api_base_url}")
    print(f"[INFO] Target Web: {settings.web_base_url}")
    print(f"[INFO] Bug Mode: {settings.demo_bug_mode or 'None'}")
    print()

    initial_state: RunState = {
        "run_id": run_id,
        "run_phase": "VALIDATING",
        "input_bundle": None,
        "test_plan": None,
        "resource_refs": ResourceRefs(),
        "auth_state": AuthState(),
        "test_results": [],
        "evidence_manifest": [],
        "errors": [],
        "evaluation": None,
        "req_paths": {
            "requirements": args.requirements,
            "openapi": args.openapi,
            "scenarios": args.scenarios,
        },
        "started_at": started_at,
        "finished_at": None,
    }

    print("[INFO] Validating input files...")
    final_state = await graph.ainvoke(initial_state)

    if final_state.get("run_phase") == "VALIDATION_FAILED":
        print("[FAIL] Input validation failed:")
        for err in final_state.get("errors", []):
            print(f"  - {err}")
        sys.exit(2)

    print("[PASS] Inputs valid")

    if final_state.get("run_phase") == "PLANNING_FAILED":
        print("[FAIL] Test planning failed:")
        for err in final_state.get("errors", []):
            print(f"  - {err}")
        sys.exit(2)

    plan = final_state.get("test_plan")
    test_count = len(plan.tests) if plan else 0
    print("[INFO] Generating test plan...")
    print(f"[PASS] {test_count} test cases generated")
    print()

    print("[INFO] Executing tests...")
    results = final_state.get("test_results", [])
    for r in results:
        status_tag = f"[{r.outcome}]"
        print(f"{status_tag} {r.test_id}: {r.observed}")

    print()
    print("[INFO] Evaluating failures and Root Cause Analysis...")
    eval_res = final_state.get("evaluation") or {}
    print(f"[INFO] RCA status: {eval_res.get('overall_verdict', 'COMPLETED')}")

    print("[INFO] Generating report and evidence logs...")
    output_dir = Path(settings.output_dir)
    print(f"[PASS] {output_dir / 'report.md'} created")
    print(f"[PASS] {output_dir / 'execution_log.json'} created")

    passed_count = sum(1 for r in results if r.outcome == "PASSED")
    failed_count = sum(1 for r in results if r.outcome in ("FAILED", "ERROR"))
    blocked_count = sum(1 for r in results if r.outcome == "BLOCKED")

    print()
    print("Execution completed")
    print(f"Passed: {passed_count}")
    print(f"Failed: {failed_count}")
    print(f"Blocked: {blocked_count}")

    # Return exit code 1 if any test failed, errored, or blocked; 0 only if all passed
    sys.exit(1 if (failed_count > 0 or blocked_count > 0 or passed_count == 0) else 0)


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
