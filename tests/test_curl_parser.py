from error_analysis.order_create.curl_builder import format_order_create_curl
from error_analysis.order_create.curl_parser import parse_order_create_curl
from error_analysis.order_create.response_check import (
    extract_globalorderid,
    find_response_check,
)


SAMPLE_CURL = format_order_create_curl(
    url="https://example.test/resellers/v6/orders",
    headers={
        "IM-CountryCode": "US",
        "IM-CustomerNumber": "60-006843",
        "Content-Type": "application/json",
    },
    body={
        "customerOrderNumber": "DEEPAKDDTEST11",
        "endCustomerOrderNumber": "DEEPAKDDTEST11",
        "lines": [{"customerLineNumber": "1", "ingramPartNumber": "X", "quantity": 1}],
    },
    username="user",
    password="pass",
)


def test_parse_order_create_curl_roundtrip():
    parsed = parse_order_create_curl(SAMPLE_CURL)
    assert parsed.url == "https://example.test/resellers/v6/orders"
    assert parsed.headers["IM-CountryCode"] == "US"
    assert parsed.headers["IM-CustomerNumber"] == "60-006843"
    assert parsed.body["customerOrderNumber"] == "DEEPAKDDTEST11"
    assert parsed.authorization is not None
    assert parsed.authorization.startswith("Basic ")


def test_extract_globalorderid():
    payload = {
        "responsepreamble": {
            "responsestatus": "FAILED",
            "statuscode": "EN",
            "responsemessage": "SKU-NOTFOUND",
        },
        "ordersummary": {
            "ordercreateresponse": [{"globalorderid": "60-75686"}]
        },
    }
    assert extract_globalorderid(payload) == "60-75686"


def test_find_response_check_includes_globalorderid_and_status():
    check = find_response_check(
        [
            {
                "log_id": "1",
                "ResponseLogPayload": {
                    "responsepreamble": {
                        "responsestatus": "FAILED",
                        "statuscode": "EN",
                        "responsemessage": "SKU-NOTFOUND",
                    },
                    "ordersummary": {
                        "ordercreateresponse": [{"globalorderid": "60-75686"}]
                    },
                },
            }
        ]
    )
    assert check is not None
    assert check.responsestatus == "FAILED"
    assert check.globalorderid == "60-75686"
    assert check.statuscode == "EN"
