"""Tests for actionable lookup-service error messages."""

from __future__ import annotations

import pytest

from error_analysis.config import Settings
from error_analysis.error_lookup.client import ErrorLookupError, lookup_error_code


@pytest.fixture
def lookup_settings() -> Settings:
    return Settings(
        DD_API_KEY="test",
        DD_APP_KEY="test",
        LOOKUP_API_URL="http://lookup.test/api/v1/lookup",
        LOOKUP_API_KEY="cobolilapp",
        LOOKUP_APPLICATION_KEY="deepakcobolil88206",
        LOOKUP_SOURCE_ROOT="C:/samples",
        LOOKUP_RULES_PATH="C:/rules.json",
        LOOKUP_CORORA_MAPPINGS="C:/mappings",
    )


def test_lookup_503_external_api_configured_message(httpx_mock, lookup_settings):
    httpx_mock.add_response(
        method="POST",
        url="http://lookup.test/api/v1/lookup",
        status_code=503,
        json={
            "detail": (
                "External lookup API is not configured. "
                "Set COBOL_EXTERNAL_API_KEY and COBOL_EXTERNAL_APPLICATION_KEY on the server."
            )
        },
    )

    with pytest.raises(ErrorLookupError) as exc:
        lookup_error_code(lookup_settings, "SE")

    msg = str(exc.value)
    assert "COBOL_EXTERNAL_API_KEY" in msg
    assert "port 8000" in msg
    assert "restart" in msg.lower()
