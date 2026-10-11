import pytest

from app.core.contract_validation import validate_response_schema
from app.executors.assertions import assert_field, assert_status, assert_text, assert_url


@pytest.mark.unit
def test_assert_status():
    p = assert_status(200, 200)
    assert p.passed is True
    assert p.message == ""

    f = assert_status(404, 200)
    assert f.passed is False
    assert "200" in f.message and "404" in f.message


@pytest.mark.unit
def test_assert_field():
    body = {
        "id": "apt_5021",
        "nested": {"status": "confirmed", "items": [{"name": "item1"}]},
    }
    assert assert_field(body, "id", "apt_5021").passed is True
    assert assert_field(body, "id", None).passed is True  # non-empty check
    assert assert_field(body, "nested.status", "confirmed").passed is True
    assert assert_field(body, "nested.items.0.name", "item1").passed is True

    # Failures
    assert assert_field(body, "nested.status", "cancelled").passed is False
    assert assert_field(body, "non_existent", "val").passed is False


@pytest.mark.unit
def test_assert_text_and_url():
    assert assert_text("Hello World Patient", "Patient").passed is True
    assert assert_text("Hello World", "Patient").passed is False

    assert assert_url("http://localhost:3000/appointments/apt_1", "/appointments/").passed is True
    assert assert_url("http://localhost:3000/login", "/dashboard").passed is False


@pytest.mark.unit
def test_validate_response_schema():
    schema = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "status": {"type": "string"},
        },
        "required": ["id", "status"],
    }

    valid_data = {"id": "123", "status": "confirmed"}
    errors = validate_response_schema(valid_data, schema)
    assert errors == []

    invalid_data = {"id": 123}  # int instead of string, missing status
    errors = validate_response_schema(invalid_data, schema)
    assert len(errors) >= 1
