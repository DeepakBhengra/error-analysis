"""API tests for POST /api/order-xml-request."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from error_analysis.datadog.fetch_request import FetchRequestResult


@pytest.fixture
def xml_settings(monkeypatch):
    monkeypatch.setenv("DD_ACCESS_TOKEN", "test-token")
    monkeypatch.delenv("DD_API_KEY", raising=False)
    monkeypatch.delenv("DD_APP_KEY", raising=False)
    from error_analysis.config import Settings

    return Settings(_env_file=None)


def _xml_record() -> dict[str, Any]:
    return {
        "log_id": "xml-log-1",
        "service": "APPPCG-Identity",
        "url": "https://10.22.102.85:22037/Processes/OrderCreate/OrderCreate_v1_0",
        "request": (
            "<soapenv:Envelope xmlns:soapenv=\"http://schemas.xmlsoap.org/soap/envelope/\""
            " xmlns:ocreq1=\"http://www.ingrammicro.com/order/OrderCreateRequest_v1_0/types\">"
            "<soapenv:Body><ocreq1:serviceRequest>"
            "<orderCreateRequest>"
            "<customerOrderNumber>DEEPAKWARRANTY1234</customerOrderNumber>"
            "</orderCreateRequest>"
            "</ocreq1:serviceRequest></soapenv:Body></soapenv:Envelope>"
        ),
    }


def _patch_fetch(monkeypatch, records: list[dict[str, Any]]):
    fetched = FetchRequestResult(
        records=records,
        query="DEEPAKWARRANTY1234 service:APPPCG-Identity",
        total_logs=len(records),
        missing_payload=0,
        request_count=len(records),
        response_count=0,
    )

    class FakeDatadogClient:
        def __init__(self, _settings):
            pass

        def __enter__(self):
            return MagicMock()

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("error_analysis.api.DatadogClient", FakeDatadogClient)
    monkeypatch.setattr(
        "error_analysis.api.fetch_xml_request_records",
        lambda *args, **kwargs: fetched,
    )


def test_order_xml_request_preview_returns_soap(xml_settings, monkeypatch):
    from error_analysis.api import app

    _patch_fetch(monkeypatch, [_xml_record()])
    client = TestClient(app)
    response = client.post(
        "/api/order-xml-request",
        json={
            "text": "DEEPAKWARRANTY1234",
            "from": "2026-11-01T00:00:00Z",
            "to": "2026-11-13T00:00:00Z",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["outcome"] == "READY"
    assert data["customerOrderNumber"] == "DEEPAKWARRANTY1234"
    assert "<orderCreateRequest>" in data["xml"]
    assert "\n      <orderCreateRequest>\n" in data["xml"]
    assert (
        "        <customerOrderNumber>DEEPAKWARRANTY1234</customerOrderNumber>"
        in data["xml"]
    )
    assert data["xml"].count("\n") >= 6
    assert data["service"] == "APPPCG-Identity"
    assert data["url"].endswith("/Processes/OrderCreate/OrderCreate_v1_0")


def test_order_xml_request_preview_404_when_empty(xml_settings, monkeypatch):
    from error_analysis.api import app

    _patch_fetch(monkeypatch, [])
    client = TestClient(app)
    response = client.post(
        "/api/order-xml-request",
        json={
            "text": "MISSINGPO",
            "from": "2026-11-01T00:00:00Z",
            "to": "2026-11-13T00:00:00Z",
        },
    )
    assert response.status_code == 404
    assert "APPPCG-Identity" in response.json()["detail"]
