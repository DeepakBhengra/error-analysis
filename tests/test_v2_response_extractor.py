import json
from pathlib import Path

from error_analysis.extractors.hermes_request import (
    extract_hermes_response,
    extract_log_payloads,
)
from error_analysis.extractors.order_create_v2_response import (
    club_impulse_order_number,
    extract_v2_response,
    parse_v2_response_text,
)
from error_analysis.order_create.response_check import (
    check_from_v2_xml,
    classify_v2_request_status,
    find_response_check,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_club_impulse_order_number():
    assert club_impulse_order_number("60", "75684") == "60-75684"
    assert club_impulse_order_number("", "75684") == "75684"
    assert club_impulse_order_number("60", "") == "60"
    assert club_impulse_order_number("", "") == ""


def test_parse_v2_response_with_pfx_prefix():
    text = (
        "OrderCreate Response "
        "<pfx5:ServiceName>OrderCreate_v2_0</pfx5:ServiceName>"
        "<pfx5:requestStatus>SUCCESS</pfx5:requestStatus>"
        "<pfx5:returnCode>0</pfx5:returnCode>"
        "<pfx5:returnMessage>SUCCESS</pfx5:returnMessage>"
        "<pfx5:orderBranchNumber>60</pfx5:orderBranchNumber>"
        "<pfx5:orderNumber>75684</pfx5:orderNumber>"
        "<pfx5:customerOrderNumber>DEEPAKDDTEST14</pfx5:customerOrderNumber>"
    )
    parsed = parse_v2_response_text(text)
    assert parsed is not None
    assert parsed["requestStatus"] == "SUCCESS"
    assert parsed["returnCode"] == "0"
    assert parsed["returnMessage"] == "SUCCESS"
    assert parsed["impulseOrderNumber"] == "60-75684"
    assert parsed["customerOrderNumber"] == "DEEPAKDDTEST14"


def test_parse_v2_response_without_prefix():
    text = (
        "OrderCreate Response "
        "<ServiceName>OrderCreate_v2_0</ServiceName>"
        "<requestStatus>FAILED</requestStatus>"
        "<returnCode>EN</returnCode>"
        "<returnMessage>SKU-NOTFOUND</returnMessage>"
        "<orderBranchNumber>60</orderBranchNumber>"
        "<orderNumber>99</orderNumber>"
        "<customerOrderNumber>PO1</customerOrderNumber>"
    )
    parsed = parse_v2_response_text(text)
    assert parsed is not None
    assert parsed["requestStatus"] == "FAILED"
    assert parsed["returnCode"] == "EN"
    assert parsed["impulseOrderNumber"] == "60-99"


def test_parse_rejects_request_only_xml():
    event = _load_fixture("order_create_v2_xml_log_event.json")
    assert extract_v2_response(event) is None


def test_parse_rejects_non_v2_service():
    text = (
        "OrderCreate Response "
        "<ServiceName>OtherService</ServiceName>"
        "<requestStatus>SUCCESS</requestStatus>"
        "<returnCode>0</returnCode>"
    )
    assert parse_v2_response_text(text) is None


def test_extract_v2_response_from_fixture():
    event = _load_fixture("order_create_v2_response_xml_log_event.json")
    parsed = extract_v2_response(event)
    assert parsed is not None
    assert parsed["impulseOrderNumber"] == "60-75684"
    assert parsed["customerOrderNumber"] == "DEEPAKDDTEST14"


def test_extract_hermes_response_returns_v2xml_wrapper():
    event = _load_fixture("order_create_v2_response_xml_log_event.json")
    response = extract_hermes_response(event)
    assert isinstance(response, dict)
    assert "v2xml" in response
    assert response["v2xml"]["returnCode"] == "0"

    request, resp = extract_log_payloads(event)
    assert resp is not None
    assert resp["v2xml"]["requestStatus"] == "SUCCESS"


def test_classify_v2_request_status():
    assert classify_v2_request_status("SUCCESS", "0") == "SUCCESS"
    assert classify_v2_request_status("SUCCESS", "200") == "SUCCESS"
    assert classify_v2_request_status("FAILED", "EN") == "FAILED"
    assert classify_v2_request_status("ERROR", "X") == "FAILED"
    assert classify_v2_request_status("PENDING", "1") == "UNKNOWN"


def test_check_from_v2_xml_success():
    event = _load_fixture("order_create_v2_response_xml_log_event.json")
    response = extract_hermes_response(event)
    record = {
        "log_id": event["id"],
        "response": response,
        "ResponseLogPayload": response,
    }
    check = check_from_v2_xml(record)
    assert check is not None
    assert check.outcome == "SUCCESS"
    assert check.statuscode == "0"
    assert check.responsemessage == "SUCCESS"
    assert check.globalorderid == "60-75684"
    assert check.customer_order_number == "DEEPAKDDTEST14"
    assert check.responsestatus == "SUCCESS"


def test_find_response_check_v2_xml_failed():
    response = {
        "v2xml": {
            "requestStatus": "FAILED",
            "returnCode": "EN",
            "returnMessage": "SKU-NOTFOUND",
            "orderBranchNumber": "60",
            "orderNumber": "1",
            "customerOrderNumber": "POFAIL",
            "impulseOrderNumber": "60-1",
            "serviceName": "OrderCreate_v2_0",
        }
    }
    check = find_response_check(
        [{"log_id": "f1", "ResponseLogPayload": response, "response": response}]
    )
    assert check is not None
    assert check.outcome == "FAILED"
    assert check.statuscode == "EN"
    assert check.responsemessage == "SKU-NOTFOUND"
    assert check.globalorderid == "60-1"
    assert check.customer_order_number == "POFAIL"


def test_find_response_check_prefers_json_preamble_over_xml():
    records = [
        {
            "log_id": "xml",
            "response": {
                "v2xml": {
                    "requestStatus": "SUCCESS",
                    "returnCode": "0",
                    "returnMessage": "SUCCESS",
                    "impulseOrderNumber": "60-1",
                    "customerOrderNumber": "X",
                }
            },
        },
        {
            "log_id": "json",
            "ResponseLogPayload": {
                "responsepreamble": {
                    "responsestatus": "FAILED",
                    "statuscode": "EN",
                    "responsemessage": "SKU-NOTFOUND",
                },
                "ordersummary": {
                    "ordercreateresponse": [{"globalorderid": "60-999"}]
                },
            },
        },
    ]
    check = find_response_check(records)
    assert check is not None
    assert check.outcome == "FAILED"
    assert check.source_log_id == "json"
    assert check.globalorderid == "60-999"


def test_parse_tns_statuscode_fragment():
    text = (
        "<tns:responsestatus>FAILED</tns:responsestatus>"
        "<tns:statuscode>EN</tns:statuscode>"
        "<tns:responsemessage>SKU-NOTFOUND    9DG827AA</tns:responsemessage>"
    )
    parsed = parse_v2_response_text(text)
    assert parsed is not None
    assert parsed["statuscode"] == "EN"
    assert parsed["responsestatus"] == "FAILED"
    assert parsed["returnCode"] == "EN"
    assert "SKU-NOTFOUND" in parsed["returnMessage"]


def test_find_response_check_prefers_two_char_failed_over_numeric():
    records = [
        {
            "log_id": "numeric",
            "ResponseLogPayload": {
                "responsepreamble": {
                    "responsestatus": "FAILED",
                    "statuscode": "406",
                    "responsemessage": "SKU-NOTFOUND    9Y7663AA",
                    "errorcode": "WZ",
                }
            },
        },
        {
            "log_id": "twochar",
            "ResponseLogPayload": {
                "responsepreamble": {
                    "responsestatus": "FAILED",
                    "statuscode": "EN",
                    "responsemessage": "SKU-NOTFOUND    9Y7663AA",
                },
                "ordersummary": {
                    "ordercreateresponse": [{"globalorderid": "60-1"}]
                },
            },
        },
    ]
    check = find_response_check(records)
    assert check is not None
    assert check.statuscode == "EN"
    assert check.source_log_id == "twochar"


def test_failed_preamble_wins_over_warning_fragment():
    """PO446552 regression: warning SUCCESS/W# fragment before FAILED preamble D9."""
    text = (
        "<tns:responsestatus>SUCCESS</tns:responsestatus>"
        "<tns:statuscode>W#</tns:statuscode>"
        "<tns:responsepreamble>"
        "<tns:responsestatus>FAILED</tns:responsestatus>"
        "<tns:statuscode>D9</tns:statuscode>"
        "<tns:responsemessage>NO-ADDR-SEQ    06KA23</tns:responsemessage>"
        "</tns:responsepreamble>"
    )
    parsed = parse_v2_response_text(text)
    assert parsed is not None
    assert parsed["responsestatus"] == "FAILED"
    assert parsed["statuscode"] == "D9"
    assert "NO-ADDR-SEQ" in parsed["responsemessage"]


def test_failed_preamble_wins_when_success_preamble_also_present():
    text = (
        "<tns:responsepreamble>"
        "<tns:responsestatus>SUCCESS</tns:responsestatus>"
        "<tns:statuscode>200</tns:statuscode>"
        "<tns:responsemessage>SUCCESS</tns:responsemessage>"
        "</tns:responsepreamble>"
        "<tns:responsepreamble>"
        "<tns:responsestatus>FAILED</tns:responsestatus>"
        "<tns:statuscode>D9</tns:statuscode>"
        "<tns:responsemessage>NO-ADDR-SEQ    06KA23</tns:responsemessage>"
        "</tns:responsepreamble>"
    )
    parsed = parse_v2_response_text(text)
    assert parsed is not None
    assert parsed["responsestatus"] == "FAILED"
    assert parsed["statuscode"] == "D9"


def test_find_response_check_failed_xml_beats_success_json():
    """A FAILED v2 XML record must win over a SUCCESS JSON preamble record."""
    xml = (
        "<tns:responsepreamble>"
        "<tns:responsestatus>FAILED</tns:responsestatus>"
        "<tns:statuscode>D9</tns:statuscode>"
        "<tns:responsemessage>NO-ADDR-SEQ    06KA23</tns:responsemessage>"
        "</tns:responsepreamble>"
    )
    records = [
        {
            "log_id": "success-json",
            "ResponseLogPayload": {
                "responsepreamble": {
                    "responsestatus": "SUCCESS",
                    "statuscode": "200",
                    "responsemessage": "SUCCESS",
                }
            },
        },
        {
            "log_id": "failed-xml",
            "message": xml,
            "ResponseLogPayload": None,
            "response": None,
        },
    ]
    check = find_response_check(records)
    assert check is not None
    assert check.outcome == "FAILED"
    assert check.source_log_id == "failed-xml"
    assert check.statuscode == "D9"
    assert "NO-ADDR-SEQ" in check.responsemessage


def test_poll_grace_waits_for_two_char_code(monkeypatch):
    """PO446552DEEPAK13 regression: numeric 400 FAILED first, D9 XML lands later."""
    from types import SimpleNamespace

    from error_analysis.order_create import replay as replay_mod

    failed_400 = {
        "log_id": "json-400",
        "ResponseLogPayload": {
            "responsepreamble": {
                "responsestatus": "FAILED",
                "statuscode": "400",
                "responsemessage": "NO-ADDR-SEQ    06KA23",
            }
        },
    }
    failed_d9_xml = {
        "log_id": "xml-d9",
        "message": (
            "<tns:responsepreamble>"
            "<tns:responsestatus>FAILED</tns:responsestatus>"
            "<tns:statuscode>D9</tns:statuscode>"
            "<tns:responsemessage>NO-ADDR-SEQ    06KA23</tns:responsemessage>"
            "</tns:responsepreamble>"
        ),
        "ResponseLogPayload": None,
        "response": None,
    }

    batches = [[failed_400], [failed_400], [failed_400, failed_d9_xml]]
    calls = {"n": 0}

    def fake_fetch(client, settings, **kwargs):
        batch = batches[min(calls["n"], len(batches) - 1)]
        calls["n"] += 1
        return SimpleNamespace(records=batch)

    monkeypatch.setattr(replay_mod, "fetch_request_records", fake_fetch)
    monkeypatch.setattr(replay_mod, "resolve_service_filter", lambda s: None)

    records = replay_mod.poll_response_logs(
        client=None,
        settings=None,
        order_number="PO446552DEEPAK13",
        from_time="2026-07-18T00:00:00Z",
        to_time="2026-07-18T23:59:59Z",
        poll_interval=0.01,
        timeout=5.0,
    )
    check = find_response_check(records)
    assert check is not None
    assert check.outcome == "FAILED"
    assert check.statuscode == "D9"
    assert check.source_log_id == "xml-d9"
    assert calls["n"] >= 3


def test_poll_grace_gives_up_and_returns_numeric(monkeypatch):
    """If no two-char code ever appears, return the numeric FAILED after grace."""
    from types import SimpleNamespace

    from error_analysis.order_create import replay as replay_mod

    failed_400 = {
        "log_id": "json-400",
        "ResponseLogPayload": {
            "responsepreamble": {
                "responsestatus": "FAILED",
                "statuscode": "400",
                "responsemessage": "NO-ADDR-SEQ    06KA23",
            }
        },
    }

    def fake_fetch(client, settings, **kwargs):
        return SimpleNamespace(records=[failed_400])

    monkeypatch.setattr(replay_mod, "fetch_request_records", fake_fetch)
    monkeypatch.setattr(replay_mod, "resolve_service_filter", lambda s: None)

    import time as time_mod

    start = time_mod.monotonic()
    records = replay_mod.poll_response_logs(
        client=None,
        settings=None,
        order_number="PO446552DEEPAK13",
        from_time="2026-07-18T00:00:00Z",
        to_time="2026-07-18T23:59:59Z",
        poll_interval=0.01,
        timeout=0.2,
    )
    elapsed = time_mod.monotonic() - start
    assert elapsed < 5.0
    check = find_response_check(records)
    assert check is not None
    assert check.statuscode == "400"


def test_find_response_check_maps_406_from_tns_statuscode_xml():
    xml = (
        "<tns:responsestatus>FAILED</tns:responsestatus>"
        "<tns:statuscode>EN</tns:statuscode>"
        "<tns:responsemessage>SKU-NOTFOUND    9DG827AA</tns:responsemessage>"
    )
    records = [
        {
            "log_id": "numeric",
            "message": xml,
            "ResponseLogPayload": {
                "responsepreamble": {
                    "responsestatus": "FAILED",
                    "statuscode": "406",
                    "responsemessage": "SKU-NOTFOUND    9DG827AA",
                }
            },
        },
    ]
    check = find_response_check(records)
    assert check is not None
    assert check.outcome == "FAILED"
    assert check.statuscode == "EN"
    assert check.source_log_id == "numeric"
    assert check.raw_preamble.get("mappedFromV2Statuscode") == "EN"
    assert check.raw_preamble.get("originalStatuscode") == "406"
