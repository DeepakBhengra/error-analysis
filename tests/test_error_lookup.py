import pytest

from error_analysis.api import _api_response
from error_analysis.config import Settings
from error_analysis.error_lookup.client import (
    ErrorLookupError,
    is_two_char_error_code,
    lookup_error_code,
    lookup_error_field,
)
from error_analysis.order_create.replay import ReplayResult


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


def test_is_two_char_error_code():
    assert is_two_char_error_code("EN") is True
    assert is_two_char_error_code("se") is True
    assert is_two_char_error_code("200") is False
    assert is_two_char_error_code("SKU") is False
    assert is_two_char_error_code("E") is False
    assert is_two_char_error_code("EN1") is False
    assert is_two_char_error_code("") is False
    assert is_two_char_error_code("  ") is False


def test_lookup_error_code_normalizes_first_finding(httpx_mock, lookup_settings):
    httpx_mock.add_response(
        method="POST",
        url="http://lookup.test/api/v1/lookup",
        json={
            "query": {"error_code": "SE", "error_field": ""},
            "program_count": 1,
            "finding_count": 1,
            "findings": [
                {
                    "error_code": "SE",
                    "error_field": "CORORA-R-ERR-NO-SEC-TERM-OVRD",
                    "program": "ORP676",
                    "line": 2707,
                    "paragraph": "100-EDIT-ACTION-REQUEST",
                    "condition": "TB-SEC-NORESP",
                    "summary": "Nested control path",
                    "historical_resolution": "INCIDENT REPORT",
                }
            ],
        },
    )

    result = lookup_error_code(lookup_settings, "se")

    assert result["error_code"] == "SE"
    assert result["error_field"] == "CORORA-R-ERR-NO-SEC-TERM-OVRD"
    assert result["historical_resolution"] == "INCIDENT REPORT"
    assert result["finding_count"] == 1

    request = httpx_mock.get_request()
    assert request is not None
    assert request.headers["X-API-Key"] == "cobolilapp"
    assert request.headers["X-Application-Key"] == "deepakcobolil88206"
    assert request.read() == (
        b'{"error_code":"SE","source_root":"C:/samples",'
        b'"rules_path":"C:/rules.json","corora_mappings":"C:/mappings"}'
    )


def test_lookup_error_code_requires_code(lookup_settings):
    with pytest.raises(ErrorLookupError, match="error_code is required"):
        lookup_error_code(lookup_settings, "  ")


def test_lookup_error_code_no_findings(httpx_mock, lookup_settings):
    httpx_mock.add_response(
        method="POST",
        url="http://lookup.test/api/v1/lookup",
        json={
            "query": {"error_code": "EN", "error_field": ""},
            "program_count": 0,
            "finding_count": 0,
            "findings": [],
        },
    )

    with pytest.raises(ErrorLookupError, match="No findings returned"):
        lookup_error_code(lookup_settings, "EN")


def test_lookup_error_field_posts_field_and_returns_code(httpx_mock, lookup_settings):
    httpx_mock.add_response(
        method="POST",
        url="http://lookup.test/api/v1/lookup",
        json={
            "query": {"error_code": "", "error_field": "ERR-NO-SEC-TERM-OVRD"},
            "program_count": 1,
            "finding_count": 1,
            "findings": [
                {
                    "error_code": "SE",
                    "error_field": "CORORA-R-ERR-NO-SEC-TERM-OVRD",
                    "program": "ORP676",
                    "line": 2707,
                    "paragraph": "100-EDIT-ACTION-REQUEST",
                    "summary": "Nested control path",
                    "historical_resolution": "INCIDENT REPORT",
                }
            ],
        },
    )

    result = lookup_error_field(lookup_settings, "ERR-NO-SEC-TERM-OVRD")

    assert result["error_code"] == "SE"
    assert result["error_field"] == "CORORA-R-ERR-NO-SEC-TERM-OVRD"

    request = httpx_mock.get_request()
    assert request is not None
    assert request.read() == (
        b'{"error_field":"ERR-NO-SEC-TERM-OVRD","source_root":"C:/samples",'
        b'"rules_path":"C:/rules.json","corora_mappings":"C:/mappings"}'
    )


def test_lookup_error_field_skips_empty_finding_code(httpx_mock, lookup_settings):
    httpx_mock.add_response(
        method="POST",
        url="http://lookup.test/api/v1/lookup",
        json={
            "query": {"error_code": "", "error_field": "ERR-X"},
            "program_count": 2,
            "finding_count": 2,
            "findings": [
                {"error_code": "", "error_field": "ERR-X"},
                {"error_code": "SE", "error_field": "CORORA-R-ERR-X"},
            ],
        },
    )

    result = lookup_error_field(lookup_settings, "ERR-X")
    assert result["error_code"] == "SE"


def test_api_response_maps_non_two_char_from_tns_statuscode(lookup_settings):
    xml = (
        "<tns:responsestatus>FAILED</tns:responsestatus>"
        "<tns:statuscode>EN</tns:statuscode>"
        "<tns:responsemessage>SKU-NOTFOUND    9DG827AA</tns:responsemessage>"
    )
    result = ReplayResult(
        customer_order_number="PO2",
        original_order_number="PO1",
        url="https://example.test/orders",
        http_status=201,
        http_body=xml,
        records=[],
        check=None,
        summary={
            "outcome": "FAILED",
            "responsestatus": "FAILED",
            "statuscode": "406",
            "responsemessage": "SKU-NOTFOUND    9DG827AA",
            "globalorderid": "60-1",
        },
        outcome="FAILED",
        curl="curl ...",
    )

    payload = _api_response(result, settings=lookup_settings, source_text="PO1")

    assert payload["statuscode"] == "EN"
    assert payload["originalStatuscode"] == "406"
    assert payload["mappedFromV2Statuscode"] == "EN"
    assert "Error Code=EN" in payload["message"]
    assert "mappedFromErrorField" not in payload


def test_api_response_maps_non_two_char_failed_statuscode(httpx_mock, lookup_settings):
    httpx_mock.add_response(
        method="POST",
        url="http://lookup.test/api/v1/lookup",
        json={
            "query": {"error_code": "", "error_field": "ERR-NO-SEC-TERM-OVRD"},
            "program_count": 1,
            "finding_count": 1,
            "findings": [
                {
                    "error_code": "SE",
                    "error_field": "CORORA-R-ERR-NO-SEC-TERM-OVRD",
                }
            ],
        },
    )

    result = ReplayResult(
        customer_order_number="PO2",
        original_order_number="PO1",
        url="https://example.test/orders",
        http_status=201,
        http_body={},
        records=[],
        check=None,
        summary={
            "outcome": "FAILED",
            "responsestatus": "FAILED",
            "statuscode": "ERR-NO-SEC-TERM-OVRD",
            "responsemessage": "ERR-NO-SEC-TERM-OVRD",
            "globalorderid": "60-1",
        },
        outcome="FAILED",
        curl="curl ...",
    )

    payload = _api_response(result, settings=lookup_settings, source_text="PO1")

    assert payload["statuscode"] == "SE"
    assert payload["originalStatuscode"] == "ERR-NO-SEC-TERM-OVRD"
    assert payload["mappedFromErrorField"] == "ERR-NO-SEC-TERM-OVRD"
    assert "Error Code=SE" in payload["message"]
    assert payload["responsemessage"] == "ERR-NO-SEC-TERM-OVRD"


def test_api_response_keeps_two_char_failed_statuscode(httpx_mock, lookup_settings):
    result = ReplayResult(
        customer_order_number="PO2",
        original_order_number="PO1",
        url="https://example.test/orders",
        http_status=201,
        http_body={},
        records=[],
        check=None,
        summary={
            "outcome": "FAILED",
            "responsestatus": "FAILED",
            "statuscode": "EN",
            "responsemessage": "SKU-NOTFOUND",
        },
        outcome="FAILED",
        curl="curl ...",
    )

    payload = _api_response(result, settings=lookup_settings)

    assert payload["statuscode"] == "EN"
    assert "originalStatuscode" not in payload
    assert httpx_mock.get_request() is None


def test_api_response_keeps_statuscode_when_lookup_fails(httpx_mock, lookup_settings):
    httpx_mock.add_response(
        method="POST",
        url="http://lookup.test/api/v1/lookup",
        status_code=500,
        text="boom",
    )

    result = ReplayResult(
        customer_order_number="PO2",
        original_order_number="PO1",
        url="https://example.test/orders",
        http_status=201,
        http_body={},
        records=[],
        check=None,
        summary={
            "outcome": "FAILED",
            "responsestatus": "FAILED",
            "statuscode": "LONGCODE",
            "responsemessage": "ERR-MISSING",
        },
        outcome="FAILED",
        curl="curl ...",
    )

    payload = _api_response(result, settings=lookup_settings)

    assert payload["statuscode"] == "LONGCODE"
    assert payload["originalStatuscode"] == "LONGCODE"
    assert payload["mappedFromErrorField"] == "ERR-MISSING"
    assert "lookupError" in payload


def test_resolve_error_code_writes_business_logic_file(httpx_mock, lookup_settings, tmp_path):
    from error_analysis.error_lookup.resolve import resolve_error_code

    httpx_mock.add_response(
        method="POST",
        url="http://lookup.test/api/v1/lookup",
        json={
            "query": {"error_code": "TC", "error_field": ""},
            "program_count": 1,
            "finding_count": 1,
            "findings": [
                {
                    "error_code": "TC",
                    "error_field": "CORORA-R-ERR-INVALID-TERMS-CODE",
                    "program": "ORP100",
                    "line": 100,
                    "paragraph": "100-EDIT",
                    "condition": "",
                    "summary": "Invalid terms",
                    "historical_resolution": "Fix terms code",
                }
            ],
        },
    )

    first = resolve_error_code(lookup_settings, "tc", results_dir=tmp_path)

    assert first["cached"] is False
    assert first["result"]["error_code"] == "TC"
    out = tmp_path / "TC Business Logic.json"
    assert out.is_file()
    assert out.name in first["path"]
    assert len(httpx_mock.get_requests()) == 1

    # Second call must not hit the lookup service
    second = resolve_error_code(lookup_settings, "TC", results_dir=tmp_path)

    assert second["cached"] is True
    assert second["result"]["error_code"] == "TC"
    assert second["result"]["historical_resolution"] == "Fix terms code"
    assert len(httpx_mock.get_requests()) == 1


def test_resolve_error_code_requires_code(lookup_settings, tmp_path):
    from error_analysis.error_lookup.resolve import resolve_error_code

    with pytest.raises(ErrorLookupError, match="error_code is required"):
        resolve_error_code(lookup_settings, "  ", results_dir=tmp_path)


def test_resolve_error_api_empty_code_returns_422():
    from fastapi.testclient import TestClient

    from error_analysis.api import app

    client = TestClient(app)
    response = client.post("/api/resolve-error", json={"error_code": ""})
    # Pydantic min_length=1 → 422
    assert response.status_code == 422
