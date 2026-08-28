"""API tests for POST /api/order-modify-request."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient

from error_analysis.api import app
from error_analysis.config import Settings
from error_analysis.datadog.fetch_request import FetchRequestResult


@dataclass
class _PreviewSettings:
    settings: Settings


@pytest.fixture
def modify_client(monkeypatch):
    settings = Settings(
        _env_file=None,
        dd_access_token="test-token",
        order_modify_test_username="APPXIMONLINE",
        order_modify_test_password="AC4PPIOine45e",
        order_create_username="APPIMEAI",
        order_create_password="App!me@!56",
    )

    def _load_settings():
        return settings

    monkeypatch.setattr("error_analysis.api._load_settings", _load_settings)
    return TestClient(app)


def _modify_record() -> dict[str, Any]:
    return {
        "log_id": "modify-1",
        "service": "OrderModify_v6_0",
        "host": "uschileai2503",
        "request": {
            "customerOrderNumber": "PO26082807111243",
            "lines": [
                {
                    "ingramPartNumber": "CJ62549",
                    "ingramLineNumber": "001",
                    "addUpdateDeleteLine": "UPDATE",
                    "quantity": 2,
                    "unitPrice": "289.81",
                }
            ],
            "additionalAttributes": [],
        },
    }


def _header_record() -> dict[str, Any]:
    return {
        "log_id": "header-1",
        "service": "OrderCreate_v2",
        "host": "uschileai2501",
        "request": {
            "ordercreaterequest": {
                "requestpreamble": {
                    "isocountrycode": "ES",
                    "customernumber": "29-001767",
                },
                "ordercreatedetails": {
                    "extendedspecs": [
                        {"attributename": "IM-SENDERID", "attributevalue": "IMX4A"},
                    ],
                },
            }
        },
    }


def _response_record() -> dict[str, Any]:
    return {
        "log_id": "response-1",
        "service": "OrderCreate_v6",
        "host": "uschileai2503",
        "response": {
            "ordersummary": {
                "ordercreateresponse": [{"globalorderid": "29-44694-11"}]
            }
        },
    }


def test_order_modify_request_preview(modify_client, monkeypatch):
    records = [_modify_record(), _header_record(), _response_record()]

    def fake_modify_fetch(*_args, **_kwargs):
        return FetchRequestResult(
            records=[records[0]],
            query='PO26082807111243 service:OrderModify_v6*',
            total_logs=1,
            missing_payload=0,
            request_count=1,
            response_count=0,
        )

    def fake_create_fetch(*_args, **_kwargs):
        return FetchRequestResult(
            records=records[1:],
            query='PO26082807111243 service:OrderCreate_v6*',
            total_logs=2,
            missing_payload=0,
            request_count=1,
            response_count=1,
        )

    monkeypatch.setattr("error_analysis.api.fetch_modify_request_records", fake_modify_fetch)
    monkeypatch.setattr("error_analysis.api.fetch_request_records", fake_create_fetch)

    res = modify_client.post(
        "/api/order-modify-request",
        json={"text": "PO26082807111243", "target": "test"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["outcome"] == "READY"
    assert "curl --location --request PUT" in data["curl"]
    assert data["orderId"] == "29-44694-11"
    assert "api-test.ingrammicro.com" in data["url"]


def test_order_modify_request_requires_username(modify_client, monkeypatch):
    def _load_settings():
        return Settings(
            _env_file=None,
            dd_access_token="test-token",
            order_modify_test_username="",
        )

    monkeypatch.setattr("error_analysis.api._load_settings", _load_settings)

    res = modify_client.post(
        "/api/order-modify-request",
        json={"text": "PO26082807111243"},
    )
    assert res.status_code == 400
    assert "ORDER_MODIFY_TEST_USERNAME" in res.json()["detail"]
