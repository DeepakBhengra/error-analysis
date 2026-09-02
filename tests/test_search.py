import json
from pathlib import Path

import httpx
import pytest

from error_analysis.config import Settings
from error_analysis.datadog.client import DatadogClient
from error_analysis.datadog.models import LogSearchFilter, LogSearchParams
from error_analysis.datadog.search import search_logs

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        DD_API_KEY="test-api-key",
        DD_APP_KEY="test-app-key",
        DD_SITE="us5.datadoghq.com",
    )


def test_search_logs_pagination(httpx_mock, settings: Settings):
    page1 = json.loads((FIXTURES / "search_page_1.json").read_text())
    page2 = json.loads((FIXTURES / "search_page_2.json").read_text())

    httpx_mock.add_response(json=page1)
    httpx_mock.add_response(json=page2)

    params = LogSearchParams(
        filter=LogSearchFilter(
            query='"G0D82"',
            **{"from": "2026-07-08T00:00:00Z", "to": "2026-07-08T01:00:00Z"},
        ),
        page_limit=50,
    )

    with DatadogClient(settings) as client:
        events = list(search_logs(client, params))

    assert len(events) == 2
    assert events[0]["id"] == "log-1"
    assert events[1]["id"] == "log-2"
    assert len(httpx_mock.get_requests()) == 2

    second_request = httpx_mock.get_requests()[1]
    body = json.loads(second_request.content)
    assert body["page"]["cursor"] == "cursor-page-2"


def test_search_logs_stops_early_before_next_page(httpx_mock, settings: Settings):
    page1 = json.loads((FIXTURES / "search_page_1.json").read_text())

    httpx_mock.add_response(json=page1)

    params = LogSearchParams(
        filter=LogSearchFilter(
            query='"G0D82"',
            **{"from": "2026-07-08T00:00:00Z", "to": "2026-07-08T01:00:00Z"},
        ),
        page_limit=50,
    )

    with DatadogClient(settings) as client:
        events = list(
            search_logs(client, params, should_stop=lambda _last_page: True)
        )

    assert len(events) == 1
    assert len(httpx_mock.get_requests()) == 1
