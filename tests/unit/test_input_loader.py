from pathlib import Path

import pytest

from app.core.input_loader import InputValidationError, load_inputs, parse_requirements


@pytest.mark.unit
def test_parse_requirements_valid():
    md = """
## REQ-001 — User Authentication
Priority: P0
- Must allow login with valid credentials.

## REQ-002 — Appointment Creation
Priority: P0
- Creates an appointment.
"""
    reqs = parse_requirements(md)
    assert len(reqs) == 2
    assert reqs[0].req_id == "REQ-001"
    assert reqs[0].priority == "P0"
    assert reqs[1].req_id == "REQ-002"


@pytest.mark.unit
def test_parse_requirements_duplicate_id_raises():
    md = """
## REQ-001 — First
Priority: P0
- Test 1

## REQ-001 — Second
Priority: P0
- Test 2
"""
    with pytest.raises(InputValidationError, match="Duplicate requirement ID"):
        parse_requirements(md)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_missing_input_file_raises(tmp_path: Path):
    non_existent = tmp_path / "does_not_exist.md"
    with pytest.raises(InputValidationError, match="Missing mandatory input file"):
        await load_inputs(non_existent, non_existent, non_existent)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_load_canonical_inputs():
    inputs_dir = Path(__file__).parent.parent.parent / "inputs"
    bundle = await load_inputs(
        inputs_dir / "requirements.md",
        inputs_dir / "openapi.json",
        inputs_dir / "scenarios.json",
    )
    assert len(bundle.requirements) >= 3
    assert len(bundle.scenarios) == 5
    assert "paths" in bundle.openapi_doc
