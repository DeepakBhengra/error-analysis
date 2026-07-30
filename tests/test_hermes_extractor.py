import json
from pathlib import Path

from error_analysis.extractors.hermes_request import (
    build_fetch_request_record,
    extract_hermes_request,
    extract_hermes_response,
    extract_log_payloads,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_extract_hermes_request_from_message_prefix():
    event = json.loads((FIXTURES / "hermes_log_event.json").read_text(encoding="utf-8"))
    request = extract_hermes_request(event)
    assert request is not None
    assert "orderquoterequest" in request
    assert request["orderquoterequest"]["lines"][0]["globalskuid"] == "A310-7140LHU"


def test_extract_hermes_request_from_nested_attributes():
    event = {
        "id": "x",
        "attributes": {
            "attributes": {
                "servicerequest": {"orderquoterequest": {"getcarrierlist": "true"}}
            }
        },
    }
    request = extract_hermes_request(event)
    assert request == {"orderquoterequest": {"getcarrierlist": "true"}}


def test_extract_hermes_request_returns_none_when_missing():
    event = {"id": "x", "attributes": {"message": "unrelated log line"}}
    assert extract_hermes_request(event) is None


def test_extract_response_log_payload_from_message():
    event = json.loads(
        (FIXTURES / "hermes_response_log_event.json").read_text(encoding="utf-8")
    )
    response = extract_hermes_response(event)
    assert response == {"status": "OK", "orderNumber": "44-12345"}


def test_extract_response_log_payload_from_attribute():
    event = {
        "id": "x",
        "attributes": {
            "attributes": {
                "ResponseLogPayload": {"status": "FAILED", "errors": ["boom"]}
            }
        },
    }
    response = extract_hermes_response(event)
    assert response == {"status": "FAILED", "errors": ["boom"]}


def test_extract_log_payloads_either_side():
    event = json.loads(
        (FIXTURES / "hermes_response_log_event.json").read_text(encoding="utf-8")
    )
    request, response = extract_log_payloads(event)
    assert request is None
    assert response is not None


def test_extract_request_log_payload_from_xml_wrapped_message():
    event = json.loads(
        (FIXTURES / "order_create_v2_xml_log_event.json").read_text(encoding="utf-8")
    )
    request = extract_hermes_request(event)
    assert request is not None
    assert request["ordercreaterequest"]["requestpreamble"]["customernumber"] == (
        "20-222222"
    )
    assert (
        request["ordercreaterequest"]["ordercreatedetails"]["customerponumber"]
        == "DELLWWEEDEEP132"
    )


def test_extract_request_from_pfx5_xml_tag_with_noise_braces():
    """Prod TIBCO logs wrap the JSON in <pfx5:RequestLogPayload> with leading
    text (e.g. 'OMP URI : ...') and other brace chunks elsewhere in the XML,
    which defeats the greedy first-to-last brace regex."""
    payload = (
        '{"ordercreaterequest":{"requestpreamble":'
        '{"isocountrycode":"US","customernumber":"41-126883"},'
        '"ordercreatedetails":{"customerponumber":"PP006564050",'
        '"shiptoaddress":{"addressline1":"TAMARA JAY"}}}}'
    )
    message = (
        "ToLog - OrderCreate_v2_0 - Request: StartNewTransactionLog <?xml "
        'version="1.0" encoding="UTF-8"?><pfx5:LogPayload '
        'xmlns:pfx5="http://www.tibco.com/schemas/EAILoggingFramework_1_0">'
        "<pfx5:ServiceName>OrderCreate_v2_0</pfx5:ServiceName>"
        "<pfx5:ServerName>uschileai1402</pfx5:ServerName>"
        "<pfx5:RequestLogPayload>OMP URI : /API/ZOMP_ORDER_CREATE_API"
        "?sap-client=100&#xD; " + payload + "</pfx5:RequestLogPayload>"
        "<pfx5:Extra>{not-json}</pfx5:Extra></pfx5:LogPayload>"
    )
    event = {"id": "prod-1", "attributes": {"message": message}}
    request = extract_hermes_request(event)
    assert request is not None
    assert (
        request["ordercreaterequest"]["ordercreatedetails"]["customerponumber"]
        == "PP006564050"
    )
    assert (
        request["ordercreaterequest"]["requestpreamble"]["customernumber"]
        == "41-126883"
    )


def test_extract_response_from_pfx5_xml_tag_with_serviceresponse():
    """v6 'OrderCreate Response formed' logs embed the JSON payload in
    <pfx5:ResponseLogPayload> inside XML with other brace noise."""
    payload = (
        '{"serviceresponse":{"responsepreamble":'
        '{"responsestatus":"SUCCESS","statuscode":"200",'
        '"responsemessage":"SUCCESS"},"ordersummary":'
        '{"customerponumber":"PO26071820472351",'
        '"ordercreateresponse":[{"globalorderid":"41-PBWWJ"}]}}}'
    )
    message = (
        'ToLog - StartNewTransactionLog <?xml version="1.0"?><pfx5:LogPayload '
        'xmlns:pfx5="http://www.tibco.com/schemas/EAILoggingFramework_1_0">'
        "<pfx5:ServiceName>OrderCreate_v6_0</pfx5:ServiceName>"
        "<pfx5:LogDescription>OrderCreate Response formed</pfx5:LogDescription>"
        "<pfx5:ResponseLogPayload>" + payload + "</pfx5:ResponseLogPayload>"
        "<pfx5:Extra>{not-json}</pfx5:Extra></pfx5:LogPayload>"
    )
    event = {"id": "v6-resp-1", "attributes": {"message": message}}
    response = extract_hermes_response(event)
    assert response is not None
    assert response["responsepreamble"]["statuscode"] == "200"
    assert (
        response["ordersummary"]["ordercreateresponse"][0]["globalorderid"]
        == "41-PBWWJ"
    )


def test_build_fetch_request_record_includes_response():
    event = json.loads((FIXTURES / "hermes_log_event.json").read_text(encoding="utf-8"))
    request = extract_hermes_request(event)
    record = build_fetch_request_record(
        event,
        request=request,
        response={"status": "OK"},
        search_text="bw0a101orlv",
        correlation_id=None,
        job_id="JOB-123",
        customer_po=None,
        env="uat",
    )
    assert record["log_id"] == "hermes-log-1"
    assert record["search_text"] == "bw0a101orlv"
    assert record["correlation_id"] is None
    assert record["request"]["orderquoterequest"]["getcarrierlist"] == "true"
    assert record["response"] == {"status": "OK"}
    assert record["RequestLogPayload"] == record["request"]
    assert record["ResponseLogPayload"] == {"status": "OK"}
