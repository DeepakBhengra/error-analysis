import base64
import json

import pytest

from error_analysis.order_modify.modify_curl_builder import (
    OrderModifyCurlError,
    build_order_modify_curl_from_records,
    format_order_modify_curl,
    resolve_order_modify_url,
)


def _sample_v2_header(
    *,
    country: str = "ES",
    customer: str = "29-001767",
    correlation: str = "38af77ca-016d-4e73-8381-9da576660a42",
    sender: str = "IMX4A",
) -> dict:
    return {
        "service": "OrderCreate_v2",
        "host": "uschileai2501",
        "request": {
            "ordercreaterequest": {
                "requestpreamble": {
                    "isocountrycode": country,
                    "customernumber": customer,
                },
                "ordercreatedetails": {
                    "customerponumber": "PO26082807111243",
                    "extendedspecs": [
                        {
                            "attributename": "IM-CORRELATIONID",
                            "attributevalue": correlation,
                        },
                        {
                            "attributename": "IM-SENDERID",
                            "attributevalue": sender,
                        },
                    ],
                },
            }
        },
    }


def _sample_modify_body() -> dict:
    return {
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
            "additionalAttributes": [
                {"attributeName": "orderdate", "attributeValue": "2026-08-28"},
                {"attributeName": "operatorid", "attributeValue": "RUL1"},
            ],
        },
    }


def _sample_create_response() -> dict:
    return {
        "service": "OrderCreate_v6",
        "host": "uschileai2503",
        "response": {
            "ordersummary": {
                "ordercreateresponse": [{"globalorderid": "29-44694-11"}]
            }
        },
    }


def test_resolve_order_modify_url_test_region():
    url = resolve_order_modify_url("29-44694-11", target="test")
    assert url == (
        "https://api-test.ingrammicro.com:443/resellers/v6/orders/29-44694-11"
    )


def test_resolve_order_modify_url_qa1_region():
    url = resolve_order_modify_url("29-44694-11", target="qa1")
    assert url == (
        "https://api-qa1.ingrammicro.com:443/resellers/v6/orders/29-44694-11"
    )


def test_build_order_modify_curl_put_with_headers_and_body():
    records = [_sample_modify_body(), _sample_v2_header(), _sample_create_response()]
    built = build_order_modify_curl_from_records(
        records,
        username="APPXIMONLINE",
        password="AC4PPIOine45e",
        target="test",
    )
    assert built.order_id == "29-44694-11"
    assert "curl --location --request PUT" in built.curl
    assert built.url.endswith("/29-44694-11")
    assert built.headers["IM-CountryCode"] == "ES"
    assert built.headers["IM-CustomerNumber"] == "29-001767"
    assert built.headers["IM-SenderID"] == "IMX4A"
    assert built.headers["Accept-Language"] == "en-us"
    assert "--data '" in built.curl
    assert built.body["customerOrderNumber"] == "PO26082807111243"
    assert built.body["lines"][0]["addUpdateDeleteLine"] == "UPDATE"

    expected_auth = base64.b64encode(b"APPXIMONLINE:AC4PPIOine45e").decode("ascii")
    assert f"Authorization: Basic {expected_auth}" in built.curl


def test_format_order_modify_curl_redacts_password():
    curl = format_order_modify_curl(
        url="https://api-test.ingrammicro.com:443/resellers/v6/orders/29-44694-11",
        headers={
            "Accept-Language": "en-us",
            "IM-CountryCode": "ES",
            "IM-CustomerNumber": "29-001767",
            "IM-CorrelationId": "abc",
            "Content-Type": "application/json",
        },
        body={"customerOrderNumber": "PO1", "lines": []},
        username="user",
        password="secret",
        redact_password=True,
    )
    assert "Authorization: Basic ***" in curl
    assert "secret" not in curl


def test_build_order_modify_requires_modify_body():
    with pytest.raises(OrderModifyCurlError, match="No OrderModify_v6"):
        build_order_modify_curl_from_records(
            [_sample_v2_header()],
            username="APPXIMONLINE",
            password="pass",
        )


def test_build_order_modify_requires_order_id():
    with pytest.raises(OrderModifyCurlError, match="Could not resolve Ingram order id"):
        build_order_modify_curl_from_records(
            [_sample_modify_body(), _sample_v2_header()],
            username="APPXIMONLINE",
            password="pass",
        )


def test_build_order_modify_accepts_explicit_order_id():
    built = build_order_modify_curl_from_records(
        [_sample_modify_body(), _sample_v2_header()],
        username="APPXIMONLINE",
        password="pass",
        order_id="29-44694-11",
        target="qa1",
    )
    assert built.target == "qa1"
    assert "api-qa1.ingrammicro.com" in built.url
