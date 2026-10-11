from typing import Any


def format_rca_markdown(findings: list[dict[str, Any]]) -> str:
    if not findings:
        return "No failures detected; no root cause analysis required.\n"

    lines = []
    for f in findings:
        lines.append(
            f"### Test Failure: `{f['test_id']}` (Requirements: {', '.join(f.get('requirement_ids', []))})"
        )
        lines.append(f"- **Observed Evidence:** {f['observed_evidence']}")
        lines.append(f"- **Root Cause Hypothesis:** {f['hypothesis']}")
        lines.append(f"- **Confidence:** {f['confidence'].upper()}")
        lines.append(f"- **Recommended Debug Action:** {f['next_debug_step']}")
        lines.append("")
    return "\n".join(lines)
