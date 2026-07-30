"""API tests for POST /api/order-request (preview, no Order Create POST)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from error_analysis.datadog.fetch_request import FetchRequestResult


@pytest.fixture
def preview_settings(monkeypatch):
    monkeypatch.setenv("DD_API_KEY", "test-dd-api")
    monkeypatch.setenv("DD_APP_KEY", "test-dd-app")
    monkeypatch.setenv("ORDER_CREATE_USERNAME", "APPIMEAI")
    monkeypatch.setenv("ORDER_CREATE_PASSWORD", "secret")
    from error_analysis.config import Settings

    return Settings()


def _v2_record() -> dict[str, Any]:
    return {
        "service": "OrderCreate_v2",
        "host": "uschileai2501",
        "request": {
            "ordercreaterequest": {
                "requestpreamble": {
                    "isocountrycode": "US",
                    "customernumber": "60-006843",
                },
                "ordercreatedetails": {
                    "customerponumber": "USREGTEST12",
                    "extendedspecs": [
                        {"attributename": "IM-CORRELATIONID", "attributevalue": "c1"},
                        {"attributename": "IM-SENDERID", "attributevalue": "portal"},
                    ],
                    "lines": [
                        {
                            "linetype": "P",
                            "ingrampartnumber": "9Y6772",
                            "quantity": 1,
                        }
                    ],
                },
            }
        },
    }


def _v6_portal_record() -> dict[str, Any]:
    return {
        "service": "OrderCreate_v6",
        "host": "uschileai2503",
        "request": {
            "customerOrderNumber": "DEEPAKDDTEST8",
            "resellerInfo": {"companyName": "Demo"},
            "lines": [{"ingramPartNumber": "9Y6772", "quantity": 1}],
        },
    }


def _malformed_record() -> dict[str, Any]:
    return {
        "service": "OrderCreate_v6",
        "host": "uschileai2503",
        "request": {"apiEndpoint": "OrderCreate_v6 API", "orderDetails": []},
    }


def _patch_fetch(monkeypatch, records: list[dict[str, Any]]):
    fetched = FetchRequestResult(
        records=records,
        query='service:(OrderCreate_v6 OR OrderCreate_v2) "USREGTEST12"',
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
        "error_analysis.api.fetch_request_records",
        lambda *args, **kwargs: fetched,
    )


def test_order_request_preview_v2_converted(preview_settings, monkeypatch):
    from error_analysis.api import app

    _patch_fetch(monkeypatch, [_v2_record()])
    client = TestClient(app)
    response = client.post(
        "/api/order-request",
        json={
            "text": "USREGTEST12",
            "from": "2026-06-01T00:00:00Z",
            "to": "2026-07-18T00:00:00Z",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["outcome"] == "READY"
    assert data["source"] == "v2-converted"
    assert data["customerOrderNumber"] == "USREGTEST12"
    assert data["body"]["customerOrderNumber"] == "USREGTEST12"
    assert "ordercreaterequest" not in data["body"]
    assert "/resellers/v6/orders" in data["curl"]
    assert "converted from Order Create v2" in data["message"]
    assert "Authorization: Basic" in data["curl"]


def test_order_request_preview_native_v6(preview_settings, monkeypatch):
    from error_analysis.api import app

    _patch_fetch(monkeypatch, [_v6_portal_record(), _v2_record()])
    client = TestClient(app)
    response = client.post(
        "/api/order-request",
        json={
            "text": "DEEPAKDDTEST8",
            "from": "2026-06-01T00:00:00Z",
            "to": "2026-07-18T00:00:00Z",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["outcome"] == "READY"
    assert data["source"] == "v6"
    assert data["body"]["resellerInfo"]["companyName"] == "Demo"
    assert "from Order Create v6 log" in data["message"]


def test_order_request_preview_asyncordercreate_qa(preview_settings, monkeypatch):
    from error_analysis.api import app

    async_record = {
        "service": "AsyncOrderCreate",
        "host": "uschileai1402",
        "request": {
            "customerOrderNumber": "PRODASYNC01",
            "resellerInfo": {"resellerId": "20222222"},
            "lines": [{"ingramPartNumber": "9Y6772", "quantity": 1}],
        },
    }
    v2_any_host = _v2_record()
    v2_any_host["host"] = "uschileai1401"
    _patch_fetch(monkeypatch, [async_record, v2_any_host])
    client = TestClient(app)
    response = client.post(
        "/api/order-request",
        json={
            "text": "PRODASYNC01",
            "from": "2026-06-01T00:00:00Z",
            "to": "2026-07-18T00:00:00Z",
            "target": "qa",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["outcome"] == "READY"
    assert data["source"] == "v6"
    assert data["target"] == "qa"
    assert data["url"].endswith("/resellers/v6/orders")
    assert "imservices-qa-usch01" in data["url"]
    assert data["body"]["customerOrderNumber"] == "PRODASYNC01"
    assert "imservices-qa-usch01" in data["curl"]


def test_order_request_preview_no_records(preview_settings, monkeypatch):
    from error_analysis.api import app

    _patch_fetch(monkeypatch, [])
    client = TestClient(app)
    response = client.post(
        "/api/order-request",
        json={
            "text": "MISSING-ORDER",
            "from": "2026-06-01T00:00:00Z",
            "to": "2026-07-18T00:00:00Z",
        },
    )
    assert response.status_code == 404
    assert "No Order Create" in response.json()["detail"]


def test_order_request_preview_malformed_records(preview_settings, monkeypatch):
    from error_analysis.api import app

    # Metadata-only v6 without a usable portal body or convertible v2.
    _patch_fetch(monkeypatch, [_malformed_record()])
    client = TestClient(app)
    response = client.post(
        "/api/order-request",
        json={
            "text": "BAD",
            "from": "2026-06-01T00:00:00Z",
            "to": "2026-07-18T00:00:00Z",
        },
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert isinstance(detail, str)
    assert detail


def test_order_request_requires_username(monkeypatch):
    monkeypatch.setenv("DD_API_KEY", "test-dd-api")
    monkeypatch.setenv("DD_APP_KEY", "test-dd-app")
    monkeypatch.setenv("ORDER_CREATE_USERNAME", "")
    monkeypatch.setenv("ORDER_CREATE_PASSWORD", "")

    from error_analysis.api import app

    client = TestClient(app)
    response = client.post(
        "/api/order-request",
        json={
            "text": "USREGTEST12",
            "from": "2026-06-01T00:00:00Z",
            "to": "2026-07-18T00:00:00Z",
        },
    )
    assert response.status_code == 400
    assert "ORDER_CREATE_USERNAME" in response.json()["detail"]


@pytest.fixture
def order_curl_settings(monkeypatch):
    monkeypatch.setenv("DD_API_KEY", "test-dd-api")
    monkeypatch.setenv("DD_APP_KEY", "test-dd-app")
    monkeypatch.setenv("ORDER_CREATE_USERNAME", "APPIMEAI")
    monkeypatch.setenv("ORDER_CREATE_PASSWORD", "secret")
    monkeypatch.setenv("ORDER_CURL_API_KEY", "test-order-curl-key")
    monkeypatch.setenv("DEFAULT_ORDER_CREATE_TARGET", "uat")
    from error_analysis.config import Settings

    return Settings()


def test_order_curl_requires_api_key(order_curl_settings, monkeypatch):
    from error_analysis.api import app

    _patch_fetch(monkeypatch, [_v6_portal_record()])
    client = TestClient(app)
    response = client.post(
        "/api/v1/order-curl",
        json={"customerOrderNumber": "DEEPAKDDTEST8"},
    )
    assert response.status_code == 401
    assert "API key" in response.json()["detail"]


def test_order_curl_rejects_invalid_api_key(order_curl_settings, monkeypatch):
    from error_analysis.api import app

    _patch_fetch(monkeypatch, [_v6_portal_record()])
    client = TestClient(app)
    response = client.post(
        "/api/v1/order-curl",
        headers={"X-API-Key": "wrong-key"},
        json={"customerOrderNumber": "DEEPAKDDTEST8"},
    )
    assert response.status_code == 401
    assert "API key" in response.json()["detail"]


def test_order_curl_success_returns_curl_only(order_curl_settings, monkeypatch):
    from error_analysis.api import app

    _patch_fetch(monkeypatch, [_v6_portal_record(), _v2_record()])
    captured: dict[str, Any] = {}

    def capture_fetch(*args, **kwargs):
        captured.update(kwargs)
        return FetchRequestResult(
            records=[_v6_portal_record(), _v2_record()],
            query='service:(OrderCreate_v6 OR OrderCreate_v2) "DEEPAKDDTEST8"',
            total_logs=2,
            missing_payload=0,
            request_count=2,
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
    monkeypatch.setattr("error_analysis.api.fetch_request_records", capture_fetch)

    client = TestClient(app)
    response = client.post(
        "/api/v1/order-curl",
        headers={"X-API-Key": "test-order-curl-key"},
        json={"customerOrderNumber": "DEEPAKDDTEST8"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    curl = response.text
    assert curl.startswith("curl --location")
    assert "/resellers/v6/orders" in curl
    assert "Authorization: Basic" in curl
    assert "DEEPAKDDTEST8" in curl
    assert captured["text"] == "DEEPAKDDTEST8"
    assert captured["from_time"]
    assert captured["to_time"]


def test_order_curl_validation_missing_order_number(order_curl_settings):
    from error_analysis.api import app

    client = TestClient(app)
    response = client.post(
        "/api/v1/order-curl",
        headers={"X-API-Key": "test-order-curl-key"},
        json={},
    )
    assert response.status_code == 422


def test_order_curl_no_records(order_curl_settings, monkeypatch):
    from error_analysis.api import app

    _patch_fetch(monkeypatch, [])
    client = TestClient(app)
    response = client.post(
        "/api/v1/order-curl",
        headers={"X-API-Key": "test-order-curl-key"},
        json={"customerOrderNumber": "MISSING-ORDER"},
    )
    assert response.status_code == 404
    assert "No Order Create" in response.json()["detail"]


def test_order_curl_unconfigured_api_key(monkeypatch):
    monkeypatch.setenv("DD_API_KEY", "test-dd-api")
    monkeypatch.setenv("DD_APP_KEY", "test-dd-app")
    monkeypatch.setenv("ORDER_CREATE_USERNAME", "APPIMEAI")
    monkeypatch.setenv("ORDER_CREATE_PASSWORD", "secret")
    monkeypatch.setenv("ORDER_CURL_API_KEY", "")

    from error_analysis.api import app

    client = TestClient(app)
    response = client.post(
        "/api/v1/order-curl",
        headers={"X-API-Key": "any-key"},
        json={"customerOrderNumber": "DEEPAKDDTEST8"},
    )
    assert response.status_code == 401
