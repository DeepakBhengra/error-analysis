import base64
import json
from pathlib import Path

import pytest

from error_analysis.order_create.curl_builder import (
    SERVICE_HOST_URL_MAP,
    UAT_ORDERS_URL,
    QA_ORDERS_URL,
    OrderCreateCurlError,
    build_order_create_curl,
    build_order_create_curl_from_records,
    build_order_create_headers,
    find_order_create_records,
    resolve_order_create_url,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _sample_v2(
    *,
    host: str = "uschileai2501",
    country: str = "US",
    customer: str = "60-006843",
    correlation: str = "123",
    sender: str = "vanessa",
) -> dict:
    return {
        "service": "OrderCreate_v2",
        "host": host,
        "request": {
            "ordercreaterequest": {
                "requestpreamble": {
                    "isocountrycode": country,
                    "customernumber": customer,
                },
                "ordercreatedetails": {
                    "customerponumber": "PO-1",
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


def _sample_v6_portal() -> dict:
    return {
        "service": "OrderCreate_v6",
        "host": "uschileai2503",
        "request": {
            "customerOrderNumber": "DEEPAKDDTEST8",
            "resellerInfo": {"companyName": "Demo"},
            "lines": [{"ingramPartNumber": "9Y6772", "quantity": 1}],
        },
    }


def _sample_v6_metadata() -> dict:
    return {
        "service": "OrderCreate_v6",
        "host": "uschileai2503",
        "request": {
            "apiEndpoint": "OrderCreate_v6 API",
            "customerOrderNumber": "DEEPAKDDTEST8",
            "orderDetails": [],
        },
    }


def test_resolve_url_v2_uat():
    assert (
        resolve_order_create_url("OrderCreate_v2", "uschileai2501") == UAT_ORDERS_URL
    )


def test_resolve_url_v6_uat():
    assert (
        resolve_order_create_url("OrderCreate_v6", "uschileai2503") == UAT_ORDERS_URL
    )


def test_build_headers_includes_correlation_sender_and_cookie():
    headers = build_order_create_headers(
        _sample_v2()["request"], cookie="sap-usercontext=sap-client=100"
    )
    assert headers["IM-CountryCode"] == "US"
    assert headers["IM-CustomerNumber"] == "60-006843"
    assert headers["IM-CorrelationID"] == "123"
    assert headers["IM-SenderID"] == "vanessa"
    assert headers["Content-Type"] == "application/json"
    assert headers["Cookie"] == "sap-usercontext=sap-client=100"
    assert list(headers)[:4] == [
        "IM-CountryCode",
        "IM-CustomerNumber",
        "IM-CorrelationID",
        "IM-SenderID",
    ]


def test_postman_curl_format_emits_real_basic_auth_by_default():
    records = [_sample_v6_metadata(), _sample_v6_portal(), _sample_v2()]
    built = build_order_create_curl_from_records(
        records,
        username="APPIMEAI",
        password="App!me@!56",
        cookie="k=v",
    )
    assert built.source == "v6"
    assert built.body["customerOrderNumber"] == "DEEPAKDDTEST8"
    assert "resellerInfo" in built.body
    assert built.curl.startswith("curl --location 'https://")
    assert "--header 'IM-CountryCode: US'" in built.curl
    assert "IM-CorrelationID: 123" in built.curl
    assert "IM-SenderID: vanessa" in built.curl
    assert "Content-Type: application/json" in built.curl
    assert "--header 'Authorization: Basic " in built.curl
    auth_pos = built.curl.index("Authorization:")
    cookie_pos = built.curl.index("Cookie:")
    assert auth_pos < cookie_pos
    assert "Cookie: k=v" in built.curl
    assert "--data-raw '" in built.curl
    expected = base64.b64encode(b"APPIMEAI:App!me@!56").decode("ascii")
    assert f"Authorization: Basic {expected}" in built.curl
    assert "Basic ***" not in built.curl
    assert "-u " not in built.curl
    assert "-X POST" not in built.curl


def test_redacts_basic_auth_when_requested():
    built = build_order_create_curl_from_records(
        [_sample_v6_portal(), _sample_v2()],
        username="APPIMEAI",
        password="secret",
        redact_password=True,
    )
    assert "Authorization: Basic ***" in built.curl
    assert "secret" not in built.curl


def test_v6_alone_requires_v2_headers():
    with pytest.raises(OrderCreateCurlError, match="OrderCreate_v2"):
        build_order_create_curl_from_records(
            [_sample_v6_portal()], username="u", password="p"
        )


def test_metadata_only_v6_record_does_not_mask_convertible_v2_body():
    """PP006564050 scenario: a metadata-only OrderCreate_v6 record (from a prior
    UAT re-submit) must not be chosen as the body when a convertible
    OrderCreate_v2* request exists — that used to raise
    'Record request is neither a portal Order Create v6 body ...'."""
    prod_v2 = _sample_v2(host="uschileai1402", country="US", customer="41-126883")
    prod_v2["service"] = "OrderCreate_v2_0"
    records = [_sample_v6_metadata(), _sample_v2(), prod_v2]
    built = build_order_create_curl_from_records(
        records,
        username="APPIMEAI",
        password="secret",
        target="uat",
    )
    assert built.source == "v2-converted"
    assert built.body["customerOrderNumber"] == "PO-1"
    assert "ordercreaterequest" not in built.body


def test_metadata_only_records_alone_raise_no_body_error():
    with pytest.raises(OrderCreateCurlError, match="No Order Create body record found"):
        build_order_create_curl_from_records(
            [_sample_v6_metadata()],
            username="u",
            password="p",
        )


def test_find_prefers_portal_v6_body():
    records = [_sample_v6_metadata(), _sample_v6_portal(), _sample_v2()]
    matches = find_order_create_records(records)
    assert len(matches) == 1
    assert "resellerInfo" in matches[0]["request"]
    assert ("OrderCreate_v6", "uschileai2503") in SERVICE_HOST_URL_MAP


def test_v2_fallback_when_no_v6():
    built = build_order_create_curl_from_records(
        [_sample_v2(host="uschleai2403")],
        username="user",
        password="pass",
    )
    assert built.url == QA_ORDERS_URL
    assert built.source == "v2-converted"
    assert built.body["customerOrderNumber"] == "PO-1"
    assert "ordercreaterequest" not in built.body
    assert "/resellers/v6/orders" in built.curl
    assert "curl --location" in built.curl
    token = base64.b64encode(b"user:pass").decode("ascii")
    assert f"Authorization: Basic {token}" in built.curl


def test_v2_test_host_uschleai3501_uses_target_url():
    """TIBCO test hosts (e.g. uschleai3501) are not prod 1401-04 but carry v2 bodies."""
    records = [_sample_v2(host="uschleai3501")]
    matches = find_order_create_records(records)
    assert len(matches) == 1
    assert matches[0]["host"] == "uschleai3501"
    built = build_order_create_curl_from_records(
        records,
        username="user",
        password="pass",
        target="uat",
    )
    assert built.url == UAT_ORDERS_URL
    assert built.source == "v2-converted"
    assert resolve_order_create_url("OrderCreate_v2", "uschleai3501", target="uat") == (
        UAT_ORDERS_URL
    )


def test_v6_portal_body_is_not_reconverted():
    built = build_order_create_curl_from_records(
        [_sample_v6_portal(), _sample_v2()],
        username="u",
        password="p",
    )
    assert built.source == "v6"
    assert built.body == _sample_v6_portal()["request"]
    assert "customerOrderNumber" in built.body
    assert "ordercreaterequest" not in built.body


def test_build_from_fixture_style_payload():
    fixture = FIXTURES / "order_create_v2_record.json"
    record = json.loads(fixture.read_text(encoding="utf-8"))
    built = build_order_create_curl(record, username="APPIMEAI", password="x")
    assert built.url.endswith("/resellers/v6/orders")
    assert built.headers["IM-CustomerNumber"] == "60-006843"
    assert built.source == "v2-converted"
    assert built.body["customerOrderNumber"] == "DEEPAKDDTEST2"
    assert "ordercreaterequest" not in built.body
    assert built.body != record["request"]
    expected = base64.b64encode(b"APPIMEAI:x").decode("ascii")
    assert f"Authorization: Basic {expected}" in built.curl


def _sample_async_v6(
    *,
    host: str = "uschileai1402",
    order_number: str = "PRODASYNC01",
) -> dict:
    return {
        "service": "AsyncOrderCreate",
        "host": host,
        "request": {
            "customerOrderNumber": order_number,
            "resellerInfo": {"resellerId": "20222222"},
            "lines": [{"ingramPartNumber": "9Y6772", "quantity": 1}],
        },
    }


def test_find_prefers_asyncordercreate_over_portal_v6():
    records = [_sample_v6_portal(), _sample_async_v6(), _sample_v2()]
    matches = find_order_create_records(records)
    assert len(matches) == 1
    assert matches[0]["service"] == "AsyncOrderCreate"
    assert matches[0]["host"] == "uschileai1402"


def test_asyncordercreate_builds_uat_curl_with_any_host_v2_headers():
    records = [
        _sample_async_v6(),
        _sample_v2(host="uschileai1401", country="US", customer="20-123456"),
    ]
    built = build_order_create_curl_from_records(
        records,
        username="APPIMEAI",
        password="secret",
        target="uat",
    )
    assert built.source == "v6"
    assert built.url == UAT_ORDERS_URL
    assert built.body_service == "AsyncOrderCreate"
    assert built.body_host == "uschileai1402"
    assert built.header_host == "uschileai1401"
    assert built.headers["IM-CountryCode"] == "US"
    assert built.headers["IM-CustomerNumber"] == "20-123456"
    assert built.body["customerOrderNumber"] == "PRODASYNC01"
    assert UAT_ORDERS_URL in built.curl
    assert "--header 'IM-CountryCode: US'" in built.curl


def test_asyncordercreate_target_qa():
    records = [
        _sample_async_v6(host="uschileai1404"),
        _sample_v2(host="uschileai9999"),
    ]
    built = build_order_create_curl_from_records(
        records,
        username="u",
        password="p",
        target="qa",
    )
    assert built.url == QA_ORDERS_URL
    assert QA_ORDERS_URL in built.curl


def test_asyncordercreate_alone_requires_v2_headers():
    with pytest.raises(OrderCreateCurlError, match="OrderCreate_v2"):
        build_order_create_curl_from_records(
            [_sample_async_v6()], username="u", password="p"
        )


def test_asyncordercreate_uses_async_metadata_headers_as_fallback():
    metadata = {
        "service": "AsyncOrderCreate",
        "host": "uschileai1402",
        "request": {
            "customerNumber": "20-999999",
            "countryCode": "US",
            "correlationId": "corr-async",
            "senderId": "portal",
            "apiEndpoint": "OrderCreate",
            "customerOrderNumber": "PRODASYNC01",
        },
    }
    built = build_order_create_curl_from_records(
        [_sample_async_v6(), metadata],
        username="u",
        password="p",
        target="uat",
    )
    assert built.headers["IM-CountryCode"] == "US"
    assert built.headers["IM-CustomerNumber"] == "20-999999"
    assert built.headers["IM-CorrelationID"] == "corr-async"
    assert built.headers["IM-SenderID"] == "portal"
    assert built.header_service == "AsyncOrderCreate"
    assert built.url == UAT_ORDERS_URL


def test_asyncordercreate_invalid_target():
    with pytest.raises(OrderCreateCurlError, match="Unsupported target"):
        build_order_create_curl_from_records(
            [_sample_async_v6(), _sample_v2(host="uschileai1401")],
            username="u",
            password="p",
            target="prod",
        )


def _sample_prod_sync_v6(
    *,
    service: str = "OrderCreate_v6_1",
    host: str = "uschileai1402",
    order_number: str = "PO446551",
) -> dict:
    return {
        "service": service,
        "host": host,
        "request": {
            "customerOrderNumber": order_number,
            "endCustomerOrderNumber": order_number,
            "resellerInfo": {"resellerId": "20222222", "countryCode": "US"},
            "lines": [{"ingramPartNumber": "GDMHFH4HN17", "quantity": 2}],
        },
    }


def test_prod_sync_v6_1_builds_uat_curl_with_v2_0_headers():
    records = [
        _sample_prod_sync_v6(),
        _sample_v2(host="uschileai1404", country="US", customer="70-839222"),
    ]
    # v2 record uses service OrderCreate_v2; also test the versioned v2_0 family
    records[1]["service"] = "OrderCreate_v2_0"
    built = build_order_create_curl_from_records(
        records,
        username="APPIMEAI",
        password="secret",
        target="uat",
    )
    assert built.source == "v6"
    assert built.url == UAT_ORDERS_URL
    assert built.body_service == "OrderCreate_v6_1"
    assert built.body_host == "uschileai1402"
    assert built.header_service == "OrderCreate_v2_0"
    assert built.header_host == "uschileai1404"
    assert built.headers["IM-CountryCode"] == "US"
    assert built.headers["IM-CustomerNumber"] == "70-839222"
    assert built.body["customerOrderNumber"] == "PO446551"


def test_prod_sync_v6_target_qa():
    records = [
        _sample_prod_sync_v6(host="uschileai1403"),
        _sample_v2(host="uschileai1404"),
    ]
    records[1]["service"] = "OrderCreate_v2_0"
    built = build_order_create_curl_from_records(
        records, username="u", password="p", target="qa"
    )
    assert built.url == QA_ORDERS_URL


def test_prod_v2_0_body_converts_to_v6_curl():
    """OrderCreate_v2_0 on a prod host with only a v2 payload (no v6 sibling)."""
    record = _sample_v2(host="uschileai1401", country="BR", customer="80-216844")
    record["service"] = "OrderCreate_v2_0"
    built = build_order_create_curl_from_records(
        [record],
        username="APPIMEAI",
        password="secret",
        target="uat",
    )
    assert built.source == "v2-converted"
    assert built.url == UAT_ORDERS_URL
    assert built.body_service == "OrderCreate_v2_0"
    assert built.body_host == "uschileai1401"
    assert built.headers["IM-CountryCode"] == "BR"
    assert built.headers["IM-CustomerNumber"] == "80-216844"
    assert built.body["customerOrderNumber"] == "PO-1"
    assert "ordercreaterequest" not in built.body


def test_prod_v2_0_body_target_qa():
    record = _sample_v2(host="uschileai1404")
    record["service"] = "OrderCreate_v2_0"
    built = build_order_create_curl_from_records(
        [record], username="u", password="p", target="qa"
    )
    assert built.url == QA_ORDERS_URL
    assert built.source == "v2-converted"


def test_prod_v6_body_still_preferred_over_prod_v2():
    v2 = _sample_v2(host="uschileai1401")
    v2["service"] = "OrderCreate_v2_0"
    records = [v2, _sample_prod_sync_v6()]
    matches = find_order_create_records(records)
    assert len(matches) == 1
    assert matches[0]["service"] == "OrderCreate_v6_1"


def _sample_v2_without_correlation(*, host: str = "uschileai1401") -> dict:
    record = _sample_v2(host=host, country="BR", customer="80-216844")
    record["service"] = "OrderCreate_v2_0"
    details = record["request"]["ordercreaterequest"]["ordercreatedetails"]
    details["extendedspecs"] = [
        {"attributename": "IM-SENDERID", "attributevalue": "portal"},
    ]
    return record


def test_prod_v2_body_uses_log_correlation_id_when_extendedspecs_missing():
    """PROD order: IM-CORRELATIONID absent from extendedspecs, but the log's
    XML wrapper CorrelationId (<pfx5:CorrelationId>) was captured on the record."""
    record = _sample_v2_without_correlation()
    record["correlation_id"] = "bw0a10kkdu-bw0a10kkdu-178438541203"
    built = build_order_create_curl_from_records(
        [record],
        username="APPIMEAI",
        password="secret",
        target="uat",
    )
    assert built.headers["IM-CorrelationID"] == "bw0a10kkdu-bw0a10kkdu-178438541203"
    assert "IM-CorrelationID: bw0a10kkdu-bw0a10kkdu-178438541203" in built.curl


def test_correlation_id_falls_back_to_sibling_record():
    """CorrelationId may live on a different log record than the body/header source."""
    body = _sample_prod_sync_v6()
    headers = _sample_v2_without_correlation(host="uschileai1404")
    sibling = {
        "service": "OrderCreate_v6_1",
        "host": "uschileai1401",
        "request": {"apiEndpoint": "OMP"},
        "correlation_id": "bw0a10kkdu-178438541203",
    }
    built = build_order_create_curl_from_records(
        [body, headers, sibling],
        username="u",
        password="p",
        target="uat",
    )
    assert built.headers["IM-CorrelationID"] == "bw0a10kkdu-178438541203"


def test_extendedspecs_correlation_preferred_over_log_correlation_id():
    record = _sample_v2(host="uschileai1401", correlation="from-extendedspecs")
    record["service"] = "OrderCreate_v2_0"
    record["correlation_id"] = "from-log-xml"
    built = build_order_create_curl_from_records(
        [record],
        username="u",
        password="p",
        target="uat",
    )
    assert built.headers["IM-CorrelationID"] == "from-extendedspecs"


def test_extract_correlation_id_from_pfx5_xml_message():
    from error_analysis.extractors.request_log_payload import extract_correlation_id

    event = {
        "attributes": {
            "message": (
                "<pfx5:LogMessage>"
                "<pfx5:CorrelationId>bw0a10kkdu-bw0a10kkdu-178438541203"
                "</pfx5:CorrelationId>"
                "<pfx5:CustomerNumber>80-216844</pfx5:CustomerNumber>"
                "</pfx5:LogMessage>"
            )
        }
    }
    assert extract_correlation_id(event) == "bw0a10kkdu-bw0a10kkdu-178438541203"


def test_prod_sync_v6_uses_v6_metadata_headers_fallback():
    metadata = {
        "service": "OrderCreate_v6_1",
        "host": "uschileai1402",
        "request": {
            "customerNumber": "70-839222",
            "countryCode": "US",
            "correlationId": "corr-sync",
            "senderId": "portal",
            "apiEndpoint": "OrderCreate",
            "customerOrderNumber": "PO446551",
        },
    }
    built = build_order_create_curl_from_records(
        [_sample_prod_sync_v6(), metadata],
        username="u",
        password="p",
        target="uat",
    )
    assert built.headers["IM-CountryCode"] == "US"
    assert built.headers["IM-CustomerNumber"] == "70-839222"
    assert built.headers["IM-CorrelationID"] == "corr-sync"
    assert built.url == UAT_ORDERS_URL