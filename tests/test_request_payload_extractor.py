import json

from error_analysis.extractors.modify_request import extract_modify_request
from error_analysis.extractors.request_payload import extract_request_payload


def test_extract_request_payload_from_message():
    message = (
        '<pfx5:RequestPayload>{"customerOrderNumber":"PO1","lines":[]}'
        "</pfx5:RequestPayload>"
    )
    event = {"attributes": {"message": message}}
    payload = extract_request_payload(event)
    assert payload == {"customerOrderNumber": "PO1", "lines": []}


def test_extract_request_payload_from_tibco_text_marker():
    message = (
        '<pfx5:RequestLogPayload>OrderNumber:- 21-G6L85-11RequestPayload:- '
        '{"customerOrderNumber":"PO26082807111243","lines":[{"ingramPartNumber":"CJ62549"}]}'
        "</pfx5:RequestLogPayload>"
    )
    event = {"attributes": {"message": message, "service": "OrderModify_v6_0"}}
    payload = extract_request_payload(event)
    assert payload["customerOrderNumber"] == "PO26082807111243"
    assert payload["lines"][0]["ingramPartNumber"] == "CJ62549"


def test_extract_order_id_from_order_number_text():
    from error_analysis.extractors.modify_request import extract_order_id_from_message

    event = {
        "message": (
            "OrderNumber:- 21-G6L85-11RequestPayload:- "
            '{"customerOrderNumber":"PO1","lines":[]}'
        )
    }
    assert extract_order_id_from_message(event) == "21-G6L85-11"


def test_extract_modify_request_from_service_log():
    event = {
        "attributes": {
            "service": "OrderModify_v6_0",
            "message": (
                '"RequestPayload": {"customerOrderNumber":"PO1","lines":[{"ingramPartNumber":"X"}]}'
            ),
        }
    }
    payload = extract_modify_request(event)
    assert payload["customerOrderNumber"] == "PO1"
    assert payload["lines"][0]["ingramPartNumber"] == "X"
