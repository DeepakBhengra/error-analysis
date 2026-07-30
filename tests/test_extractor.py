import json
from pathlib import Path

from error_analysis.extractors.request_log_payload import (
    build_result_record,
    extract_request_log_payload,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_extract_from_nested_attributes():
    event = _load_fixture("sample_log_event.json")
    payload = extract_request_log_payload(event)
    assert payload == {
        "requestId": "G0D82",
        "method": "POST",
        "path": "/api/orders",
    }


def test_extract_with_custom_path():
    event = _load_fixture("sample_log_event.json")
    payload = extract_request_log_payload(
        event, payload_path="attributes.attributes.RequestLogPayload"
    )
    assert payload["requestId"] == "G0D82"


def test_extract_from_message_json():
    event = {
        "id": "x",
        "attributes": {
            "message": json.dumps(
                {"RequestLogPayload": {"requestId": "MSG1", "status": "ok"}}
            )
        },
    }
    payload = extract_request_log_payload(event)
    assert payload == {"requestId": "MSG1", "status": "ok"}


def test_extract_returns_none_when_missing():
    event = {"id": "x", "attributes": {"message": "no payload here"}}
    assert extract_request_log_payload(event) is None


def test_build_result_record():
    event = _load_fixture("sample_log_event.json")
    payload = {"requestId": "G0D82"}
    record = build_result_record(event, payload)
    assert record["log_id"] == event["id"]
    assert record["service"] == "my-service"
    assert record["request_log_payload"] == payload
