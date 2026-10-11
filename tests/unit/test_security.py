import pytest

from app.core.security import (
    SecurityError,
    assert_allowed_url,
    is_allowed_host,
    redact_headers,
    sanitize_for_prompt,
)


@pytest.mark.unit
def test_allowed_hosts():
    assert is_allowed_host("http://localhost:8001/api/appointments") is True
    assert is_allowed_host("http://demo-api:8001/healthz") is True
    assert is_allowed_host("http://malicious-site.com/api") is False
    assert is_allowed_host("file:///etc/passwd") is False


@pytest.mark.unit
def test_assert_allowed_url_raises():
    with pytest.raises(SecurityError, match="Target host or scheme not permitted"):
        assert_allowed_url("http://unauthorized-domain.com")

    with pytest.raises(SecurityError):
        assert_allowed_url("file:///local/path")


@pytest.mark.unit
def test_redact_headers():
    headers = {
        "Authorization": "Bearer super-secret-jwt-token",
        "Content-Type": "application/json",
        "Cookie": "session_id=12345",
    }
    redacted = redact_headers(headers)
    assert redacted["Authorization"] == "[REDACTED]"
    assert redacted["Cookie"] == "[REDACTED]"
    assert redacted["Content-Type"] == "application/json"


@pytest.mark.unit
def test_sanitize_for_prompt():
    data = {
        "user_email": "test@example.com",
        "password": "SecretPassword123!",
        "access_token": "token-123",
        "meta": {"status": "ok", "token": "abc"},
    }
    sanitized = sanitize_for_prompt(data)
    assert "password" not in sanitized
    assert "access_token" not in sanitized
    assert sanitized["user_email"] == "test@example.com"
    assert "token" not in sanitized["meta"]
    assert sanitized["meta"]["status"] == "ok"
