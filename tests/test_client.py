import json
from pathlib import Path

import httpx
import pytest

from error_analysis.config import Settings
from error_analysis.datadog.client import DatadogClient
from error_analysis.datadog.errors import DatadogAuthError

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        DD_API_KEY="test-api-key",
        DD_APP_KEY="test-app-key",
        DD_SITE="us5.datadoghq.com",
    )


def test_validate_credentials_success(httpx_mock, settings: Settings):
    httpx_mock.add_response(json={"valid": True})

    with DatadogClient(settings) as client:
        result = client.validate_credentials()

    assert result["valid"] is True
    request = httpx_mock.get_requests()[0]
    assert request.headers["DD-API-KEY"] == "test-api-key"
    assert request.headers["DD-APPLICATION-KEY"] == "test-app-key"
    assert str(request.url).endswith("/api/v1/validate")


def test_validate_credentials_auth_error(httpx_mock, settings: Settings):
    httpx_mock.add_response(status_code=403, text="Forbidden")

    with DatadogClient(settings) as client:
        with pytest.raises(DatadogAuthError):
            client.validate_credentials()


def test_access_token_uses_bearer_auth(httpx_mock):
    settings = Settings(
        DD_ACCESS_TOKEN="ddpat_test-token-value",
        DD_SITE="us5.datadoghq.com",
    )
    httpx_mock.add_response(json={"data": []})

    with DatadogClient(settings) as client:
        result = client.validate_credentials()

    assert result["valid"] is True
    assert result["auth"] == "access_token"
    request = httpx_mock.get_requests()[0]
    assert request.headers["Authorization"] == "Bearer ddpat_test-token-value"
    assert "DD-API-KEY" not in request.headers
    assert "DD-APPLICATION-KEY" not in request.headers
    assert str(request.url).endswith("/api/v2/logs/events/search")


def test_access_token_preferred_over_api_keys(httpx_mock):
    settings = Settings(
        DD_ACCESS_TOKEN="token-wins",
        DD_API_KEY="ignored-api",
        DD_APP_KEY="ignored-app",
        DD_SITE="us5.datadoghq.com",
    )
    httpx_mock.add_response(json={"data": []})

    with DatadogClient(settings) as client:
        client.search_logs({"filter": {"query": "*"}})

    request = httpx_mock.get_requests()[0]
    assert request.headers["Authorization"] == "Bearer token-wins"
    assert "DD-API-KEY" not in request.headers
