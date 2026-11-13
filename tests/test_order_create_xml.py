"""Extract and fetch Order Create SOAP XML from APPPCG-Identity logs."""

from __future__ import annotations

import json
from pathlib import Path

from error_analysis.datadog.fetch_request import fetch_xml_request_records
from error_analysis.extractors.order_create_xml import (
    XML_ORDER_CREATE_PATH,
    extract_customer_order_number,
    extract_http_url,
    extract_order_create_xml,
    format_order_create_xml,
    is_order_create_xml_event,
    redact_xml_credentials,
)

FIXTURE = Path(__file__).parent / "fixtures" / "apppcg_identity_xml_log_event.json"


def _event() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_extracts_soap_request_and_redacts_credential():
    event = _event()
    xml = extract_order_create_xml(event)
    assert xml is not None
    assert "<orderCreateRequest>" in xml
    assert "DEEPAKWARRANTY1234" in xml
    assert "<credential>***</credential>" in xml
    assert "super-secret" not in xml
    assert extract_customer_order_number(xml) == "DEEPAKWARRANTY1234"
    assert extract_http_url(event).endswith(XML_ORDER_CREATE_PATH)
    assert "\n  <soapenv:Header>" in xml
    assert "\n    <ocreq1:serviceRequest>" in xml
    assert xml.count("\n") >= 8


def test_ignores_logs_for_other_identity_urls():
    event = _event()
    event["attributes"]["attributes"]["http"]["url"] = (
        "https://10.22.102.85:22037/Processes/OrderModify/OrderModify_v1_0"
    )
    event["attributes"]["attributes"]["http"]["url_details"]["path"] = (
        "/Processes/OrderModify/OrderModify_v1_0"
    )
    event["attributes"]["attributes"]["soapaction"] = "/Processes/OrderModify"
    assert is_order_create_xml_event(event) is False


def test_ignores_other_services():
    event = _event()
    event["attributes"]["service"] = "OrderCreate_v2_0"
    assert is_order_create_xml_event(event) is False


def test_format_order_create_xml_indents_minified_soap():
    compact = (
        '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
        "<soapenv:Body><orderCreateRequest>"
        "<customerOrderNumber>PO1</customerOrderNumber>"
        "</orderCreateRequest></soapenv:Body></soapenv:Envelope>"
    )
    formatted = format_order_create_xml(compact)
    assert formatted.startswith("<soapenv:Envelope")
    assert "\n  <soapenv:Body>\n    <orderCreateRequest>" in formatted
    assert "<customerOrderNumber>PO1</customerOrderNumber>" in formatted


def test_format_order_create_xml_keeps_leaf_text_on_one_line():
    compact = (
        "<Envelope><Body><orderCreateRequest>"
        "<customerOrderNumber>PO1</customerOrderNumber>"
        "<shipToAddress/>"
        "<emailAddress></emailAddress>"
        "</orderCreateRequest></Body></Envelope>"
    )
    formatted = format_order_create_xml(compact)
    assert "<customerOrderNumber>PO1</customerOrderNumber>" in formatted
    assert "\n      <shipToAddress/>\n" in formatted
    assert "<emailAddress></emailAddress>" in formatted
    assert format_order_create_xml(formatted) == formatted


def test_redact_is_idempotent():
    xml = "<credential>***</credential>"
    assert redact_xml_credentials(xml) == xml


def test_fetch_xml_request_records_keeps_matching_event(monkeypatch):
    event = _event()
    other = json.loads(json.dumps(event))
    other["id"] = "other"
    other["attributes"]["attributes"]["http"]["url"] = (
        "https://10.22.102.85:22037/Processes/SomethingElse"
    )
    other["attributes"]["attributes"]["http"]["url_details"]["path"] = (
        "/Processes/SomethingElse"
    )

    def fake_search_logs(_client, _params, should_stop=None):
        for item in (other, event):
            yield item
            if should_stop is not None and should_stop(True):
                return

    monkeypatch.setattr(
        "error_analysis.datadog.fetch_request.search_logs",
        fake_search_logs,
    )

    class FakeSettings:
        default_storage_tier = "indexes"
        default_sort = "-timestamp"
        default_page_limit = 50

    result = fetch_xml_request_records(
        object(),
        FakeSettings(),  # type: ignore[arg-type]
        from_time="2026-11-01T00:00:00Z",
        to_time="2026-11-13T00:00:00Z",
        text="DEEPAKWARRANTY1234",
    )
    assert result.query == "DEEPAKWARRANTY1234 service:APPPCG-Identity"
    assert len(result.records) == 1
    assert result.records[0]["log_id"] == "xml-log-1"
    assert "super-secret" not in result.records[0]["request"]
    assert result.records[0]["url"].endswith(XML_ORDER_CREATE_PATH)
