"""ORRORH copybook vs OrderUpdate Substation Request report."""

from error_analysis.order_create.orrorh_report import (
    COPYBOOK_START_FIELD,
    SPACES_VALUE,
    build_orrorh_report_lines,
    extract_substation_xml,
    extract_substation_xml_from_event,
    is_order_create_v2_event,
    is_order_update_substation_event,
    lookup_orrorh_from_events,
    orrorh_copybook_fields,
    parse_orrorh_fields,
    parse_orrorh_xml_values,
    report_from_substation_xml,
)

SUBSTATION_XML = """\
<ns0:SSOrderEntryRequest xmlns:ns0="http://www.ingrammicro.com/SSOrderEntryRequest">
    <ORRORH-PAYMENT-CODE/>
    <ORRORH-CREDIT-CARD-NO/>
    <ORRORH-REQUEST-FUNCTION>OR</ORRORH-REQUEST-FUNCTION>
    <ORRORH-CUSTOMER-BR>30</ORRORH-CUSTOMER-BR>
    <ORRORH-CUSTOMER-NBR>395650</ORRORH-CUSTOMER-NBR>
    <ORRORH-CUST-TO-ING-PO-NBR>P27951377</ORRORH-CUST-TO-ING-PO-NBR>
    <ORRORH-ADDRESS-OVERRIDE-FLAG> </ORRORH-ADDRESS-OVERRIDE-FLAG>
    <ORRORD-DETAIL-ELEMENTS>CLORC HEADER SHOULD BE IGNORED</ORRORD-DETAIL-ELEMENTS>
    <ORRORH-SHIP-CTAC-EMAIL>user@example.com</ORRORH-SHIP-CTAC-EMAIL>
    <ORRORH-ORDER-FTZ-FLAG/>
</ns0:SSOrderEntryRequest>
"""

WRAPPED_PAYLOAD = (
    "<ns0:RequestLogPayload>Substation Request: {&#xD;"
    '<?xml version="1.0" encoding="UTF-8"?>'
    f"{SUBSTATION_XML}"
    "&#xD;}</ns0:RequestLogPayload>"
)

COPYBOOK_SNIPPET = """\
002300 01  ORRORH-ORDER-REQUEST.
002400     05  ORRORH-REQUEST-FUNCTION         PIC X(02).
002500         88  ORRORH-CREATE-ORDER                    VALUE 'OR'.
002700     05  ORRORH-CUSTOMER-BR              PIC X(02).
002800     05  ORRORH-CUSTOMER-NBR             PIC X(06).
           05  ORRORH-SHIP-TO-ADDRESS-5.
               15 ORRORH-SHIP-TO-PHONE           PIC X(15).
     05  ORRORH-FILLER-AREA             PIC X(10).
     05  ORRORH-CREDIT-CARD-NO         PIC X(20).
"""


def test_parse_orrorh_fields_starts_at_request_function():
    names = parse_orrorh_fields(COPYBOOK_SNIPPET)
    assert names[0] == COPYBOOK_START_FIELD
    assert "ORRORH-CUSTOMER-BR" in names
    assert "ORRORH-SHIP-TO-PHONE" in names
    assert "ORRORH-CREDIT-CARD-NO" in names
    assert "ORRORH-CREATE-ORDER" not in names
    assert "ORRORH-SHIP-TO-ADDRESS-5" not in names
    assert "ORRORH-FILLER-AREA" not in names
    assert "ORRORH-ORDER-REQUEST" not in names


def test_packaged_copybook_starts_with_request_function():
    names = orrorh_copybook_fields()
    assert names[0] == "ORRORH-REQUEST-FUNCTION"
    assert "ORRORH-CUSTOMER-BR" in names
    assert "ORRORD-DETAIL-ELEMENTS" not in names
    assert all(not name.startswith("ORRORD-") for name in names)
    assert all("FILLER" not in name for name in names)


def test_extract_substation_xml_unescapes_request_log_payload():
    xml = extract_substation_xml(WRAPPED_PAYLOAD)
    assert xml.startswith("<ns0:SSOrderEntryRequest")
    assert "ORRORH-REQUEST-FUNCTION" in xml
    assert "&#xD;" not in xml


def test_empty_and_self_closing_tags_are_spaces():
    values = parse_orrorh_xml_values(SUBSTATION_XML)
    assert values["ORRORH-REQUEST-FUNCTION"] == "OR"
    assert "ORRORH-CREDIT-CARD-NO" not in values
    assert "ORRORH-PAYMENT-CODE" not in values
    assert "ORRORH-ADDRESS-OVERRIDE-FLAG" not in values
    assert "ORRORD-DETAIL-ELEMENTS" not in values

    lines = build_orrorh_report_lines(
        SUBSTATION_XML,
        fields=(
            "ORRORH-REQUEST-FUNCTION",
            "ORRORH-CREDIT-CARD-NO",
            "ORRORH-CUSTOMER-BR",
            "ORRORH-ADDRESS-OVERRIDE-FLAG",
            "ORRORH-SHIP-CTAC-EMAIL",
        ),
    )
    assert lines[0] == "1. ORRORH-REQUEST-FUNCTION = OR"
    assert lines[1] == f"2. ORRORH-CREDIT-CARD-NO = {SPACES_VALUE}"
    assert lines[2] == "3. ORRORH-CUSTOMER-BR = 30"
    assert lines[3] == f"4. ORRORH-ADDRESS-OVERRIDE-FLAG = {SPACES_VALUE}"
    assert lines[4] == "5. ORRORH-SHIP-CTAC-EMAIL = user@example.com"


def test_report_uses_order_ftz_flag_alias():
    lines = build_orrorh_report_lines(
        SUBSTATION_XML,
        fields=("ORRORH-ORDER-FTZ-FLAG-SW",),
    )
    assert lines[0] == f"1. ORRORH-ORDER-FTZ-FLAG-SW = {SPACES_VALUE}"


def test_full_copybook_report_ignores_detail_elements():
    report = report_from_substation_xml(SUBSTATION_XML)
    assert "1. ORRORH-REQUEST-FUNCTION = OR" in report.report
    assert "ORRORH-CREDIT-CARD-NO = Spaces" in report.report
    assert "ORRORD-DETAIL-ELEMENTS" not in report.report
    assert "CLORC HEADER" not in report.report


def test_identify_v2_and_substation_events():
    v2_event = {
        "id": "v2-1",
        "attributes": {
            "service": "OrderCreate_v2_0",
            "message": (
                "<ns0:ServiceName>OrderCreate_v2_0</ns0:ServiceName>"
                "<customerOrderNumber>P27951377</customerOrderNumber>"
            ),
        },
    }
    update_event = {
        "id": "upd-1",
        "attributes": {
            "service": "OrderUpdate_Service_root",
            "LogDescription": "OrderCreateCallSubstationRequest",
            "RequestLogPayload": WRAPPED_PAYLOAD,
        },
    }
    assert is_order_create_v2_event(v2_event, "P27951377") is True
    assert is_order_create_v2_event(v2_event, "OTHER") is False
    assert is_order_update_substation_event(update_event) is True
    xml = extract_substation_xml_from_event(update_event)
    assert "ORRORH-REQUEST-FUNCTION" in xml

    result = lookup_orrorh_from_events(
        v2_events=[v2_event],
        update_events=[update_event],
        order_number="P27951377",
    )
    assert result.v2_found is True
    assert result.source_log_id == "upd-1"
    assert result.report.startswith("1. ORRORH-REQUEST-FUNCTION = OR")
    assert "2. ORRORH-CUSTOMER-BR = 30" in result.report
