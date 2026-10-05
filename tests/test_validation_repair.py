"""Tests for validation-driven Order Create curl repair."""

from __future__ import annotations

import re
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from error_analysis.api import _api_response
from error_analysis.config import Settings
from error_analysis.order_create.curl_parser import parse_order_create_curl
from error_analysis.order_create.replay import ReplayResult
from error_analysis.order_create.response_check import ResponseCheckResult
from error_analysis.order_create.validation_repair import (
    extract_validation_fields,
    repair_order_create_curl,
)

_SAMPLE_CURL = """\
curl --location 'https://example.test/resellers/v6/orders' \\
--header 'IM-CountryCode: BR' \\
--header 'IM-CustomerNumber: 80-216844' \\
--header 'Content-Type: application/json' \\
--header 'Authorization: Basic QVBQSU1FQUk6c2VjcmV0' \\
--data-raw '{
    "customerOrderNumber": "3084862875730626B4",
    "billToAddressId": "000",
    "lines": [
        {
            "customerLineNumber": "001",
            "globalSkuId": "A309-AA25185",
            "quantity": 1
        }
    ]
}'
"""

_VALIDATION_BODY = {
    "errors": [
        {
            "id": "-bw0a101r8-2026-07-18T08:59:19.398-07:00",
            "type": "/errors/validation-failed",
            "message": "Validation failed",
            "fields": [
                {
                    "field": "IM-CorrelationId",
                    "value": "",
                    "message": "IM-CorrelationId cannot be blank",
                }
            ],
        }
    ]
}


@pytest.fixture
def repair_settings() -> Settings:
    return Settings(
        DD_API_KEY="test",
        DD_APP_KEY="test",
        ORDER_CREATE_USERNAME="APPIMEAI",
        ORDER_CREATE_PASSWORD="secret",
    )


def test_extract_validation_fields_from_errors():
    fields = extract_validation_fields(_VALIDATION_BODY)
    assert len(fields) == 1
    assert fields[0].field == "IM-CorrelationId"
    assert fields[0].value == ""
    assert "cannot be blank" in fields[0].message


def test_extract_validation_fields_non_json():
    assert extract_validation_fields("not json") == []
    assert extract_validation_fields(None) == []
    assert extract_validation_fields({"ok": True}) == []


def test_repair_adds_im_correlation_id_uuid():
    result = repair_order_create_curl(
        _SAMPLE_CURL,
        _VALIDATION_BODY,
        username="APPIMEAI",
        password="secret",
    )
    assert result.repaired is True
    assert result.repaired_fields == ["IM-CorrelationId"]
    assert result.unresolved_fields == []
    assert "IM-CorrelationId" in result.curl
    assert "cannot be blank" not in result.curl

    parsed = parse_order_create_curl(result.curl)
    corr = parsed.headers.get("IM-CorrelationId") or parsed.headers.get("IM-CorrelationID")
    assert corr is not None
    assert corr.strip() != ""
    assert re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        corr,
        flags=re.IGNORECASE,
    )
    assert parsed.body["customerOrderNumber"] == "3084862875730626B4"
    assert parsed.headers["IM-CountryCode"] == "BR"
    assert "Re-Submit" in result.message


def test_repair_is_case_insensitive_for_correlation_id():
    body = {
        "errors": [
            {
                "fields": [
                    {
                        "field": "im-correlationid",
                        "value": "",
                        "message": "blank",
                    }
                ]
            }
        ]
    }
    result = repair_order_create_curl(
        _SAMPLE_CURL,
        body,
        username="APPIMEAI",
        password="secret",
    )
    assert result.repaired is True
    assert "IM-CorrelationId" in result.repaired_fields


def test_repair_preserves_existing_nonblank_correlation_id():
    curl_with_corr = _SAMPLE_CURL.replace(
        "--header 'Content-Type: application/json' \\",
        "--header 'IM-CorrelationId: already-set' \\\n"
        "--header 'Content-Type: application/json' \\",
    )
    result = repair_order_create_curl(
        curl_with_corr,
        _VALIDATION_BODY,
        username="APPIMEAI",
        password="secret",
    )
    assert result.repaired is False
    assert "already-set" in result.curl


def test_repair_reports_unresolved_body_fields():
    body = {
        "errors": [
            {
                "fields": [
                    {
                        "field": "billToAddressId",
                        "value": "",
                        "message": "billToAddressId cannot be blank",
                    }
                ]
            }
        ]
    }
    result = repair_order_create_curl(
        _SAMPLE_CURL,
        body,
        username="APPIMEAI",
        password="secret",
    )
    assert result.repaired is False
    assert result.unresolved_fields == ["billToAddressId"]
    assert "cannot be safely inferred" in result.message
    assert result.curl == _SAMPLE_CURL


def test_repair_mixed_deterministic_and_unresolved():
    body = {
        "errors": [
            {
                "fields": [
                    {
                        "field": "IM-CorrelationId",
                        "value": "",
                        "message": "blank",
                    },
                    {
                        "field": "creditCardDetails.cardNumber",
                        "value": "",
                        "message": "blank",
                    },
                ]
            }
        ]
    }
    result = repair_order_create_curl(
        _SAMPLE_CURL,
        body,
        username="APPIMEAI",
        password="secret",
    )
    assert result.repaired is True
    assert result.repaired_fields == ["IM-CorrelationId"]
    assert result.unresolved_fields == ["creditCardDetails.cardNumber"]
    assert "Still unresolved" in result.message


def test_repair_restores_missing_content_type():
    curl_no_ct = _SAMPLE_CURL.replace(
        "--header 'Content-Type: application/json' \\\n",
        "",
    )
    body = {
        "errors": [
            {
                "fields": [
                    {
                        "field": "Content-Type",
                        "value": "",
                        "message": "Content-Type cannot be blank",
                    }
                ]
            }
        ]
    }
    result = repair_order_create_curl(
        curl_no_ct,
        body,
        username="APPIMEAI",
        password="secret",
    )
    assert result.repaired is True
    parsed = parse_order_create_curl(result.curl)
    assert parsed.headers["Content-Type"] == "application/json"


def test_api_response_includes_http_body_and_repair(repair_settings):
    curl = _SAMPLE_CURL
    result = ReplayResult(
        customer_order_number="3084862875730626B5",
        original_order_number="3084862875730626B4",
        url="https://example.test/resellers/v6/orders",
        http_status=400,
        http_body=_VALIDATION_BODY,
        records=[],
        check=None,
        summary={
            "outcome": "TIMEOUT",
            "responsestatus": "",
            "statuscode": "",
            "responsemessage": "",
            "globalorderid": "",
            "http_body": _VALIDATION_BODY,
        },
        outcome="TIMEOUT",
        curl=curl,
    )

    payload = _api_response(result, settings=repair_settings)

    assert payload["http_status"] == 400
    assert payload["http_body"] == _VALIDATION_BODY
    assert payload["curlRepaired"] is True
    assert payload["repairedFields"] == ["IM-CorrelationId"]
    assert "IM-CorrelationId" in payload["curl"]
    assert payload["curl"] != curl
    assert "Repaired curl" in payload["message"]


def test_api_response_http_body_without_repairable_fields(repair_settings):
    result = ReplayResult(
        customer_order_number="PO2",
        original_order_number="PO1",
        url="https://example.test/orders",
        http_status=201,
        http_body={"accepted": True},
        records=[],
        check=None,
        summary={"outcome": "SUCCESS", "statuscode": "00"},
        outcome="SUCCESS",
        curl=_SAMPLE_CURL,
    )
    payload = _api_response(result, settings=repair_settings)
    assert payload["http_body"] == {"accepted": True}
    assert payload["curlRepaired"] is False
    assert payload["repairedFields"] == []
    assert payload["curl"] == _SAMPLE_CURL


def test_resubmit_api_returns_http_body_and_repaired_curl(monkeypatch):
    monkeypatch.setenv("DD_API_KEY", "test-dd-api")
    monkeypatch.setenv("DD_APP_KEY", "test-dd-app")
    monkeypatch.setenv("ORDER_CREATE_USERNAME", "APPIMEAI")
    monkeypatch.setenv("ORDER_CREATE_PASSWORD", "secret")

    from error_analysis import api as api_module
    from error_analysis.config import Settings

    monkeypatch.setattr(api_module, "_load_settings", lambda: Settings())

    post_calls: list[dict] = []

    def fake_post_order_create(**kwargs):
        post_calls.append(kwargs)
        return 400, _VALIDATION_BODY

    def fake_poll(*args, **kwargs):
        return []

    class FakeDatadogClient:
        def __init__(self, _settings):
            pass

        def __enter__(self):
            return MagicMock()

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        "error_analysis.order_create.replay.post_order_create",
        fake_post_order_create,
    )
    monkeypatch.setattr(
        "error_analysis.order_create.replay.poll_response_logs",
        fake_poll,
    )
    monkeypatch.setattr(
        "error_analysis.order_create.replay.poll_corora_statuscode",
        fake_poll,
    )
    monkeypatch.setattr(
        "error_analysis.order_create.replay.poll_orrorh_report",
        lambda *args, **kwargs: __import__(
            "error_analysis.order_create.orrorh_report",
            fromlist=["empty_orrorh_result"],
        ).empty_orrorh_result(),
    )
    monkeypatch.setattr(
        "error_analysis.order_create.replay.DatadogClient",
        FakeDatadogClient,
    )

    client = TestClient(api_module.app)
    response = client.post(
        "/api/resubmit",
        json={
            "curl": _SAMPLE_CURL,
            "mode": "one_up",
            "timeout": 1,
            "poll_interval": 0.1,
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["http_status"] == 400
    assert data["http_body"] == _VALIDATION_BODY
    assert data["curlRepaired"] is True
    assert "IM-CorrelationId" in data["curl"]
    # Repair must not trigger a second POST.
    assert len(post_calls) == 1


def test_resubmit_success_falls_back_to_http_body_globalorderid(monkeypatch):
    """Datadog SUCCESS log without ordersummary: impulse order number must be
    recovered from the immediate HTTP response body."""
    monkeypatch.setenv("DD_API_KEY", "test-dd-api")
    monkeypatch.setenv("DD_APP_KEY", "test-dd-app")
    monkeypatch.setenv("ORDER_CREATE_USERNAME", "APPIMEAI")
    monkeypatch.setenv("ORDER_CREATE_PASSWORD", "secret")

    from error_analysis import api as api_module
    from error_analysis.config import Settings

    monkeypatch.setattr(api_module, "_load_settings", lambda: Settings())

    http_body = {
        "serviceresponse": {
            "responsepreamble": {
                "responsestatus": "SUCCESS",
                "statuscode": "200",
                "responsemessage": "SUCCESS",
            },
            "ordersummary": {
                "ordercreateresponse": [{"globalorderid": "41-PBWWJ"}]
            },
        }
    }

    def fake_post_order_create(**kwargs):
        return 200, http_body

    def fake_poll(*args, **kwargs):
        # v6 SUCCESS response log without ordersummary/globalorderid,
        # and no sibling record carrying the id either.
        return [
            {
                "log_id": "v6",
                "service": "OrderCreate_v6_0",
                "ResponseLogPayload": {
                    "responsepreamble": {
                        "responsestatus": "SUCCESS",
                        "statuscode": "200",
                        "responsemessage": "SUCCESS",
                    }
                },
            }
        ]

    class FakeDatadogClient:
        def __init__(self, _settings):
            pass

        def __enter__(self):
            return MagicMock()

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        "error_analysis.order_create.replay.post_order_create",
        fake_post_order_create,
    )
    monkeypatch.setattr(
        "error_analysis.order_create.replay.poll_response_logs",
        fake_poll,
    )
    monkeypatch.setattr(
        "error_analysis.order_create.replay.poll_orrorh_report",
        lambda *args, **kwargs: __import__(
            "error_analysis.order_create.orrorh_report",
            fromlist=["empty_orrorh_result"],
        ).empty_orrorh_result(),
    )
    monkeypatch.setattr(
        "error_analysis.order_create.replay.DatadogClient",
        FakeDatadogClient,
    )

    client = TestClient(api_module.app)
    response = client.post(
        "/api/resubmit",
        json={
            "curl": _SAMPLE_CURL,
            "mode": "one_up",
            "timeout": 1,
            "poll_interval": 0.1,
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["outcome"] == "SUCCESS"
    assert data["globalorderid"] == "41-PBWWJ"


def test_resubmit_does_not_poll_datadog(monkeypatch):
    monkeypatch.setenv("DD_API_KEY", "test-dd-api")
    monkeypatch.setenv("DD_APP_KEY", "test-dd-app")
    monkeypatch.setenv("ORDER_CREATE_USERNAME", "APPIMEAI")
    monkeypatch.setenv("ORDER_CREATE_PASSWORD", "secret")

    from error_analysis import api as api_module
    from error_analysis.config import Settings

    monkeypatch.setattr(api_module, "_load_settings", lambda: Settings())

    http_body = {
        "serviceresponse": {
            "responsepreamble": {
                "responsestatus": "SUCCESS",
                "statuscode": "200",
                "responsemessage": "SUCCESS",
            },
            "ordersummary": {
                "ordercreateresponse": [{"globalorderid": "30-FAST1"}]
            },
        }
    }

    def fake_post(**kwargs):
        return 200, http_body

    def fake_poll(*args, **kwargs):
        raise AssertionError("Re-Submit must not poll Datadog")

    class FakeDatadogClient:
        def __init__(self, _settings):
            raise AssertionError("Re-Submit must not open Datadog")

    monkeypatch.setattr(
        "error_analysis.order_create.replay.post_order_create",
        fake_post,
    )
    monkeypatch.setattr(
        "error_analysis.order_create.replay.poll_response_logs",
        fake_poll,
    )
    monkeypatch.setattr(
        "error_analysis.order_create.replay.poll_orrorh_report",
        lambda *args, **kwargs: __import__(
            "error_analysis.order_create.orrorh_report",
            fromlist=["empty_orrorh_result"],
        ).empty_orrorh_result(),
    )
    monkeypatch.setattr(
        "error_analysis.order_create.replay.DatadogClient",
        FakeDatadogClient,
    )

    client = TestClient(api_module.app)
    response = client.post(
        "/api/resubmit",
        json={"curl": _SAMPLE_CURL, "mode": "one_up"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["outcome"] == "SUCCESS"
    assert data["globalorderid"] == "30-FAST1"
    assert data["statuscode"] == "200"
    assert data["responsemessage"] == "SUCCESS"
    assert data["http_status"] == 200
    assert data["http_body"] == http_body
    assert "Success report: SUCCESS." in data["message"]
    assert "Code: 200." in data["message"]
    assert "Impulse Order Number: 30-FAST1." in data["message"]


def test_resubmit_rest_success_shows_impulse_message_and_code(monkeypatch):
    """REST v6 success has numeric ingramOrderNumber; UI must show 30-Q6HX2."""
    monkeypatch.setenv("DD_API_KEY", "test-dd-api")
    monkeypatch.setenv("DD_APP_KEY", "test-dd-app")
    monkeypatch.setenv("ORDER_CREATE_USERNAME", "APPIMEAI")
    monkeypatch.setenv("ORDER_CREATE_PASSWORD", "secret")

    from error_analysis import api as api_module
    from error_analysis.config import Settings

    monkeypatch.setattr(api_module, "_load_settings", lambda: Settings())

    http_body = {
        "customerOrderNumber": "PO-00008219",
        "orders": [{"ingramOrderNumber": "7109517746"}],
    }

    def fake_post(**kwargs):
        return 200, http_body

    def fake_impulse_poll(*args, **kwargs):
        return [
            {
                "log_id": "v6",
                "service": "OrderCreate_v6_0",
                "ResponseLogPayload": {
                    "serviceresponse": {
                        "responsepreamble": {
                            "responsestatus": "SUCCESS",
                            "statuscode": "200",
                            "responsemessage": "SUCCESS",
                        },
                        "ordersummary": {
                            "ordercreateresponse": [{"globalorderid": "30-Q6HX2"}]
                        },
                    }
                },
            }
        ]

    class FakeDatadogClient:
        def __init__(self, _settings):
            pass

        def __enter__(self):
            return MagicMock()

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        "error_analysis.order_create.replay.post_order_create",
        fake_post,
    )
    monkeypatch.setattr(
        "error_analysis.order_create.replay.poll_impulse_order_id",
        fake_impulse_poll,
    )
    monkeypatch.setattr(
        "error_analysis.order_create.replay.poll_orrorh_report",
        lambda *args, **kwargs: __import__(
            "error_analysis.order_create.orrorh_report",
            fromlist=["empty_orrorh_result"],
        ).empty_orrorh_result(),
    )
    monkeypatch.setattr(
        "error_analysis.order_create.replay.DatadogClient",
        FakeDatadogClient,
    )

    client = TestClient(api_module.app)
    response = client.post(
        "/api/resubmit",
        json={"curl": _SAMPLE_CURL, "mode": "one_up"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["outcome"] == "SUCCESS"
    assert data["responsestatus"] == "SUCCESS"
    assert data["statuscode"] == "200"
    assert data["responsemessage"] == "SUCCESS"
    assert data["globalorderid"] == "30-Q6HX2"
    assert data["globalorderid"] != "7109517746"
    assert "Success report: SUCCESS." in data["message"]
    assert "Code: 200." in data["message"]
    assert "Impulse Order Number: 30-Q6HX2." in data["message"]


def test_resubmit_rest_success_omits_numeric_ingram_when_datadog_has_no_impulse(
    monkeypatch,
):
    monkeypatch.setenv("DD_API_KEY", "test-dd-api")
    monkeypatch.setenv("DD_APP_KEY", "test-dd-app")
    monkeypatch.setenv("ORDER_CREATE_USERNAME", "APPIMEAI")
    monkeypatch.setenv("ORDER_CREATE_PASSWORD", "secret")

    from error_analysis import api as api_module
    from error_analysis.config import Settings

    monkeypatch.setattr(api_module, "_load_settings", lambda: Settings())

    http_body = {
        "customerOrderNumber": "PO-00008219",
        "orders": [{"ingramOrderNumber": "7109517746"}],
    }

    def fake_post(**kwargs):
        return 200, http_body

    def fake_impulse_poll(*args, **kwargs):
        return []

    class FakeDatadogClient:
        def __init__(self, _settings):
            pass

        def __enter__(self):
            return MagicMock()

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        "error_analysis.order_create.replay.post_order_create",
        fake_post,
    )
    monkeypatch.setattr(
        "error_analysis.order_create.replay.poll_impulse_order_id",
        fake_impulse_poll,
    )
    monkeypatch.setattr(
        "error_analysis.order_create.replay.poll_orrorh_report",
        lambda *args, **kwargs: __import__(
            "error_analysis.order_create.orrorh_report",
            fromlist=["empty_orrorh_result"],
        ).empty_orrorh_result(),
    )
    monkeypatch.setattr(
        "error_analysis.order_create.replay.DatadogClient",
        FakeDatadogClient,
    )

    client = TestClient(api_module.app)
    response = client.post(
        "/api/resubmit",
        json={"curl": _SAMPLE_CURL, "mode": "one_up"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["outcome"] == "SUCCESS"
    assert data["statuscode"] == "200"
    assert data["responsemessage"] == "SUCCESS"
    assert data["globalorderid"] == ""
    assert "7109517746" not in (data["message"] or "")
    assert "Success report: SUCCESS." in data["message"]
    assert "Code: 200." in data["message"]


def _failed_xml_records(statuscode: str, message: str) -> list[dict]:
    xml = (
        "<tns:responsestatus>FAILED</tns:responsestatus>"
        f"<tns:statuscode>{statuscode}</tns:statuscode>"
        f"<tns:responsemessage>{message}</tns:responsemessage>"
    )
    return [{"log_id": "xml", "message": xml, "ResponseLogPayload": xml}]


def test_resubmit_failed_uses_datadog_xml_statuscode_em(monkeypatch):
    """HTTP 400 CUSTOMER-PO-EXISTS must show Datadog <tns:statuscode>EM, not COBOL BM."""
    monkeypatch.setenv("DD_API_KEY", "test-dd-api")
    monkeypatch.setenv("DD_APP_KEY", "test-dd-app")
    monkeypatch.setenv("ORDER_CREATE_USERNAME", "APPIMEAI")
    monkeypatch.setenv("ORDER_CREATE_PASSWORD", "secret")

    from error_analysis import api as api_module
    from error_analysis.config import Settings

    monkeypatch.setattr(api_module, "_load_settings", lambda: Settings())

    http_body = {"errors": [{"message": "CUSTOMER-PO-EXISTS"}]}

    def fake_post(**kwargs):
        return 400, http_body

    def fake_corora_poll(*args, **kwargs):
        return _failed_xml_records("EM", "CUSTOMER-PO-EXISTS")

    def fail_cobol(*args, **kwargs):
        raise AssertionError("COBOL lookup must not replace Datadog XML statuscode")

    class FakeDatadogClient:
        def __init__(self, _settings):
            pass

        def __enter__(self):
            return MagicMock()

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        "error_analysis.order_create.replay.post_order_create",
        fake_post,
    )
    monkeypatch.setattr(
        "error_analysis.order_create.replay.poll_corora_statuscode",
        fake_corora_poll,
    )
    monkeypatch.setattr(
        "error_analysis.order_create.replay.poll_orrorh_report",
        lambda *args, **kwargs: __import__(
            "error_analysis.order_create.orrorh_report",
            fromlist=["empty_orrorh_result"],
        ).empty_orrorh_result(),
    )
    monkeypatch.setattr(
        "error_analysis.order_create.replay.DatadogClient",
        FakeDatadogClient,
    )
    monkeypatch.setattr(
        "error_analysis.api.lookup_error_field",
        fail_cobol,
    )

    client = TestClient(api_module.app)
    response = client.post(
        "/api/resubmit",
        json={"curl": _SAMPLE_CURL, "mode": "one_up"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["outcome"] == "FAILED"
    assert data["statuscode"] == "EM"
    assert data["responsemessage"] == "CUSTOMER-PO-EXISTS"
    assert "Error Code=EM" in data["message"]
    assert data["statuscode"] != "BM"
    assert data["statuscode"] != "400"


def test_resubmit_failed_uses_last_two_chars_of_lulaen(monkeypatch):
    monkeypatch.setenv("DD_API_KEY", "test-dd-api")
    monkeypatch.setenv("DD_APP_KEY", "test-dd-app")
    monkeypatch.setenv("ORDER_CREATE_USERNAME", "APPIMEAI")
    monkeypatch.setenv("ORDER_CREATE_PASSWORD", "secret")

    from error_analysis import api as api_module
    from error_analysis.config import Settings

    monkeypatch.setattr(api_module, "_load_settings", lambda: Settings())

    http_body = {"errors": [{"message": "SKU-NOTFOUND    9DG827AA"}]}

    def fake_post(**kwargs):
        return 400, http_body

    def fake_corora_poll(*args, **kwargs):
        return _failed_xml_records("LULAEN", "SKU-NOTFOUND    9DG827AA")

    def fail_cobol(*args, **kwargs):
        raise AssertionError("COBOL lookup must not replace Datadog XML statuscode")

    class FakeDatadogClient:
        def __init__(self, _settings):
            pass

        def __enter__(self):
            return MagicMock()

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        "error_analysis.order_create.replay.post_order_create",
        fake_post,
    )
    monkeypatch.setattr(
        "error_analysis.order_create.replay.poll_corora_statuscode",
        fake_corora_poll,
    )
    monkeypatch.setattr(
        "error_analysis.order_create.replay.poll_orrorh_report",
        lambda *args, **kwargs: __import__(
            "error_analysis.order_create.orrorh_report",
            fromlist=["empty_orrorh_result"],
        ).empty_orrorh_result(),
    )
    monkeypatch.setattr(
        "error_analysis.order_create.replay.DatadogClient",
        FakeDatadogClient,
    )
    monkeypatch.setattr(
        "error_analysis.api.lookup_error_field",
        fail_cobol,
    )

    client = TestClient(api_module.app)
    response = client.post(
        "/api/resubmit",
        json={"curl": _SAMPLE_CURL, "mode": "one_up"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["outcome"] == "FAILED"
    assert data["statuscode"] == "EN"
    assert "SKU-NOTFOUND" in data["responsemessage"]
    assert "Error Code=EN" in data["message"]
    assert data["statuscode"] != "LULAEN"
    assert data["statuscode"] != "400"


_PO_CURL = """\
curl --location 'https://example.test/resellers/v6/orders' \\
--header 'Content-Type: application/json' \\
--header 'Authorization: Basic QVBQSU1FQUk6c2VjcmV0' \\
--data-raw '{
    "customerOrderNumber": "P27951376",
    "endCustomerOrderNumber": "P27951376",
    "billToAddressId": "000"
}'
"""


def _patch_replay_post(monkeypatch, fake_post):
    def fake_poll(*args, **kwargs):
        return [
            {
                "log_id": "v6",
                "service": "OrderCreate_v6_0",
                "ResponseLogPayload": {
                    "customerOrderNumber": "P27951376",
                    "responsepreamble": {
                        "responsestatus": "SUCCESS",
                        "statuscode": "200",
                        "responsemessage": "SUCCESS",
                    },
                },
            }
        ]

    class FakeDatadogClient:
        def __init__(self, _settings):
            pass

        def __enter__(self):
            return MagicMock()

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        "error_analysis.order_create.replay.post_order_create",
        fake_post,
    )
    monkeypatch.setattr(
        "error_analysis.order_create.replay.poll_response_logs",
        fake_poll,
    )
    monkeypatch.setattr(
        "error_analysis.order_create.replay.poll_orrorh_report",
        lambda *args, **kwargs: __import__(
            "error_analysis.order_create.orrorh_report",
            fromlist=["empty_orrorh_result"],
        ).empty_orrorh_result(),
    )
    monkeypatch.setattr(
        "error_analysis.order_create.replay.DatadogClient",
        FakeDatadogClient,
    )


def test_api_response_keeps_replayed_customer_order_number(repair_settings):
    check = ResponseCheckResult(
        outcome="SUCCESS",
        statuscode="200",
        responsemessage="SUCCESS",
        errorcode="",
        responsestatus="SUCCESS",
        globalorderid="30-Q6HX2",
        raw_preamble={},
        response_payload={},
        source_log_id="1",
        customer_order_number="P27951376",
    )
    result = ReplayResult(
        customer_order_number="P27951377",
        original_order_number="P27951376",
        url="https://example.test/orders",
        http_status=200,
        http_body={"ok": True},
        records=[],
        check=check,
        summary={
            "outcome": "SUCCESS",
            "responsestatus": "SUCCESS",
            "statuscode": "200",
            "responsemessage": "SUCCESS",
            "globalorderid": "30-Q6HX2",
            "customerOrderNumber": "P27951377",
            "originalCustomerOrderNumber": "P27951376",
        },
        outcome="SUCCESS",
        curl=_PO_CURL.replace("P27951376", "P27951377"),
    )
    payload = _api_response(result, settings=repair_settings)
    assert payload["customerOrderNumber"] == "P27951377"
    assert payload["originalCustomerOrderNumber"] == "P27951376"
    assert payload["globalorderid"] == "30-Q6HX2"
    assert payload["statuscode"] == "200"
    assert payload["responsemessage"] == "SUCCESS"
    assert "Success report: SUCCESS." in payload["message"]
    assert "Code: 200." in payload["message"]
    assert "Impulse Order Number: 30-Q6HX2." in payload["message"]


def test_resubmit_one_up_updates_customer_and_end_po(monkeypatch):
    monkeypatch.setenv("DD_API_KEY", "test-dd-api")
    monkeypatch.setenv("DD_APP_KEY", "test-dd-app")
    monkeypatch.setenv("ORDER_CREATE_USERNAME", "APPIMEAI")
    monkeypatch.setenv("ORDER_CREATE_PASSWORD", "secret")

    from error_analysis import api as api_module
    from error_analysis.config import Settings

    monkeypatch.setattr(api_module, "_load_settings", lambda: Settings())

    post_calls: list[dict] = []

    def fake_post(**kwargs):
        post_calls.append(kwargs)
        return 200, {"ok": True}

    _patch_replay_post(monkeypatch, fake_post)

    client = TestClient(api_module.app)
    response = client.post(
        "/api/resubmit",
        json={
            "curl": _PO_CURL,
            "mode": "one_up",
            "timeout": 1,
            "poll_interval": 0.1,
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert post_calls[0]["body"]["customerOrderNumber"] == "P27951377"
    assert post_calls[0]["body"]["endCustomerOrderNumber"] == "P27951377"
    assert len(data["customerOrderNumber"]) <= 18
    assert data["customerOrderNumber"] == "P27951377"
    assert data["originalCustomerOrderNumber"] == "P27951376"
    assert '"customerOrderNumber": "P27951377"' in data["curl"]
    assert '"endCustomerOrderNumber": "P27951377"' in data["curl"]


def test_resubmit_uses_saved_settings_mode_when_request_omits_mode(monkeypatch):
    monkeypatch.setenv("DD_API_KEY", "test-dd-api")
    monkeypatch.setenv("DD_APP_KEY", "test-dd-app")
    monkeypatch.setenv("ORDER_CREATE_USERNAME", "APPIMEAI")
    monkeypatch.setenv("ORDER_CREATE_PASSWORD", "secret")
    monkeypatch.setenv("DEFAULT_REPLAY_MODE", "one_up")

    from error_analysis import api as api_module
    from error_analysis.config import Settings

    monkeypatch.setattr(api_module, "_load_settings", lambda: Settings())

    post_calls: list[dict] = []

    def fake_post(**kwargs):
        post_calls.append(kwargs)
        return 200, {"ok": True}

    _patch_replay_post(monkeypatch, fake_post)

    client = TestClient(api_module.app)
    response = client.post("/api/resubmit", json={"curl": _PO_CURL})
    assert response.status_code == 200, response.text
    assert post_calls[0]["body"]["customerOrderNumber"] == "P27951377"
    assert post_calls[0]["body"]["endCustomerOrderNumber"] == "P27951377"
    assert response.json()["customerOrderNumber"] == "P27951377"


def test_resubmit_saved_random_mode_without_request_mode(monkeypatch):
    monkeypatch.setenv("DD_API_KEY", "test-dd-api")
    monkeypatch.setenv("DD_APP_KEY", "test-dd-app")
    monkeypatch.setenv("ORDER_CREATE_USERNAME", "APPIMEAI")
    monkeypatch.setenv("ORDER_CREATE_PASSWORD", "secret")
    monkeypatch.setenv("DEFAULT_REPLAY_MODE", "random")

    from error_analysis import api as api_module
    from error_analysis.config import Settings
    from error_analysis.order_create import order_number as order_number_mod

    monkeypatch.setattr(api_module, "_load_settings", lambda: Settings())
    monkeypatch.setattr(order_number_mod.random, "choices", lambda _alphabet, k: ["X"] * k)

    post_calls: list[dict] = []

    def fake_post(**kwargs):
        post_calls.append(kwargs)
        return 200, {"ok": True}

    _patch_replay_post(monkeypatch, fake_post)

    client = TestClient(api_module.app)
    response = client.post("/api/resubmit", json={"curl": _PO_CURL})
    assert response.status_code == 200, response.text
    posted = post_calls[0]["body"]["customerOrderNumber"]
    assert posted != "P27951376"
    assert len(posted) <= 18
    assert posted == post_calls[0]["body"]["endCustomerOrderNumber"]
    assert response.json()["customerOrderNumber"] == posted


def test_resubmit_random_updates_customer_and_end_po(monkeypatch):
    monkeypatch.setenv("DD_API_KEY", "test-dd-api")
    monkeypatch.setenv("DD_APP_KEY", "test-dd-app")
    monkeypatch.setenv("ORDER_CREATE_USERNAME", "APPIMEAI")
    monkeypatch.setenv("ORDER_CREATE_PASSWORD", "secret")

    from error_analysis import api as api_module
    from error_analysis.config import Settings
    from error_analysis.order_create import order_number as order_number_mod

    monkeypatch.setattr(api_module, "_load_settings", lambda: Settings())
    monkeypatch.setattr(order_number_mod.random, "choices", lambda _alphabet, k: ["X"] * k)

    post_calls: list[dict] = []

    def fake_post(**kwargs):
        post_calls.append(kwargs)
        return 200, {"ok": True}

    _patch_replay_post(monkeypatch, fake_post)

    client = TestClient(api_module.app)
    response = client.post(
        "/api/resubmit",
        json={
            "curl": _PO_CURL,
            "mode": "random",
            "timeout": 1,
            "poll_interval": 0.1,
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    posted = post_calls[0]["body"]["customerOrderNumber"]
    assert posted != "P27951376"
    assert posted.startswith("P")
    assert len(posted) <= 18
    assert posted == post_calls[0]["body"]["endCustomerOrderNumber"]
    assert data["customerOrderNumber"] == posted
    assert data["originalCustomerOrderNumber"] == "P27951376"


def test_resubmit_includes_orrorh_substation_report(monkeypatch):
    monkeypatch.setenv("DD_API_KEY", "test-dd-api")
    monkeypatch.setenv("DD_APP_KEY", "test-dd-app")
    monkeypatch.setenv("ORDER_CREATE_USERNAME", "APPIMEAI")
    monkeypatch.setenv("ORDER_CREATE_PASSWORD", "secret")

    from error_analysis import api as api_module
    from error_analysis.config import Settings
    from error_analysis.order_create.orrorh_report import report_from_substation_xml

    monkeypatch.setattr(api_module, "_load_settings", lambda: Settings())

    xml = """
    <ns0:SSOrderEntryRequest xmlns:ns0="http://www.ingrammicro.com/SSOrderEntryRequest">
        <ORRORH-REQUEST-FUNCTION>OR</ORRORH-REQUEST-FUNCTION>
        <ORRORH-CUSTOMER-BR>30</ORRORH-CUSTOMER-BR>
        <ORRORH-CREDIT-CARD-NO/>
        <ORRORD-DETAIL-ELEMENTS>IGNORE ME</ORRORD-DETAIL-ELEMENTS>
    </ns0:SSOrderEntryRequest>
    """
    lookup = report_from_substation_xml(xml)
    lookup = lookup.__class__(
        report=lookup.report,
        fields=lookup.fields,
        xml=xml,
        v2_found=True,
        source_log_id="upd-1",
        comment_records=lookup.comment_records,
        line_records=lookup.line_records,
    )

    def fake_post(**kwargs):
        return 200, {
            "serviceresponse": {
                "responsepreamble": {
                    "responsestatus": "SUCCESS",
                    "statuscode": "200",
                    "responsemessage": "SUCCESS",
                },
                "ordersummary": {
                    "ordercreateresponse": [{"globalorderid": "30-Q6HX2"}]
                },
            }
        }

    class FakeDatadogClient:
        def __init__(self, _settings):
            raise AssertionError("poll_orrorh_report should be stubbed")

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        "error_analysis.order_create.replay.post_order_create",
        fake_post,
    )
    monkeypatch.setattr(
        "error_analysis.order_create.replay.poll_orrorh_report",
        lambda *args, **kwargs: lookup,
    )
    monkeypatch.setattr(
        "error_analysis.order_create.replay.DatadogClient",
        FakeDatadogClient,
    )

    client = TestClient(api_module.app)
    response = client.post(
        "/api/resubmit",
        json={"curl": _SAMPLE_CURL, "mode": "one_up"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["outcome"] == "SUCCESS"
    assert data["orrorhReport"].startswith("1. ORRORH-REQUEST-FUNCTION = OR")
    assert "ORRORH-CUSTOMER-BR = 30" in data["orrorhReport"]
    assert "ORRORH-CREDIT-CARD-NO = Spaces" in data["orrorhReport"]
    assert "ORRORD-DETAIL-ELEMENTS" not in data["orrorhReport"]
    assert data["orrorhFields"][0]["name"] == "ORRORH-REQUEST-FUNCTION"
    assert data["orrorhFields"][0]["value"] == "OR"
    assert data["orrorhFields"][0]["conditions"][0]["name"] == "ORRORH-CREATE-ORDER"
    assert data["orrorcRecords"] == []
    assert data["orrorlRecords"] == []
