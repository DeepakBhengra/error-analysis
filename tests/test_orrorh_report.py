"""ORRORH copybook vs OrderUpdate Substation Request report."""

from error_analysis.config import Settings
from error_analysis.order_create.orrorh_report import (
    COPYBOOK_START_FIELD,
    ORDER_UPDATE_SERVICE_FILTER,
    SPACES_VALUE,
    SUBSTATION_LOG_DESCRIPTION,
    build_orrorh_report_lines,
    build_substation_search_query,
    extract_substation_xml,
    extract_substation_xml_from_event,
    fetch_orrorh_lookup,
    find_substation_xml,
    is_order_create_v2_event,
    is_order_update_substation_event,
    lookup_orrorh_from_events,
    orrorh_copybook_fields,
    orrorh_copybook_model,
    parse_orrorh_copybook,
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
     05  ORRORH-BCK-BACKORDER-FLAG       PIC X(01).
         88 ORRORH-BCK-VALID-BO-FLAG     VALUE 'Y' 'N' 'C' 'P'    ROR10293
                                               'E' 'B'.           ROR10293
         88 ORRORH-BCK-ALLOW-BACKORDERS             VALUE 'Y'.
         88 ORRORH-BCK-NO-BACKORDERS                VALUE 'N'.
         88 ORRORH-BCK-SHIP-COMPLETE     VALUE 'C' 'E' 'B'.
         88 ORRORH-BCK-SHIP-CONSOLIDATED            VALUE 'B'.
         88 ORRORH-BCK-FILL-COMPLETE                VALUE 'P'.
     05  ORRORH-SS-SPLIT-SHIP-FLAG       PIC X(01).
         88 ORRORH-SS-SPLIT-SHIP-VALID         VALUE 'Y', 'N'.
"""


def test_parse_orrorh_fields_starts_at_request_function():
    names = parse_orrorh_fields(COPYBOOK_SNIPPET)
    assert names[0] == COPYBOOK_START_FIELD
    assert "ORRORH-CUSTOMER-BR" in names
    assert "ORRORH-SHIP-TO-PHONE" in names
    assert "ORRORH-CREDIT-CARD-NO" in names
    assert "ORRORH-BCK-BACKORDER-FLAG" in names
    assert "ORRORH-CREATE-ORDER" not in names
    assert "ORRORH-BCK-ALLOW-BACKORDERS" not in names
    assert "ORRORH-SHIP-TO-ADDRESS-5" not in names
    assert "ORRORH-FILLER-AREA" not in names
    assert "ORRORH-ORDER-REQUEST" not in names


def test_parse_88_conditions_attach_to_parent_pic():
    model = {field.name: field for field in parse_orrorh_copybook(COPYBOOK_SNIPPET)}
    create = model["ORRORH-REQUEST-FUNCTION"]
    assert create.conditions[0].name == "ORRORH-CREATE-ORDER"
    assert create.conditions[0].values == ("OR",)

    flag = model["ORRORH-BCK-BACKORDER-FLAG"]
    names = [item.name for item in flag.conditions]
    assert names == [
        "ORRORH-BCK-VALID-BO-FLAG",
        "ORRORH-BCK-ALLOW-BACKORDERS",
        "ORRORH-BCK-NO-BACKORDERS",
        "ORRORH-BCK-SHIP-COMPLETE",
        "ORRORH-BCK-SHIP-CONSOLIDATED",
        "ORRORH-BCK-FILL-COMPLETE",
    ]
    by_name = {item.name: item.values for item in flag.conditions}
    assert by_name["ORRORH-BCK-VALID-BO-FLAG"] == ("Y", "N", "C", "P", "E", "B")
    assert by_name["ORRORH-BCK-ALLOW-BACKORDERS"] == ("Y",)
    assert by_name["ORRORH-BCK-SHIP-COMPLETE"] == ("C", "E", "B")
    assert model["ORRORH-CUSTOMER-BR"].conditions == ()


def test_packaged_copybook_backorder_flag_has_88s():
    model = {field.name: field for field in orrorh_copybook_model()}
    flag = model["ORRORH-BCK-BACKORDER-FLAG"]
    assert [item.name for item in flag.conditions] == [
        "ORRORH-BCK-VALID-BO-FLAG",
        "ORRORH-BCK-ALLOW-BACKORDERS",
        "ORRORH-BCK-NO-BACKORDERS",
        "ORRORH-BCK-SHIP-COMPLETE",
        "ORRORH-BCK-SHIP-CONSOLIDATED",
        "ORRORH-BCK-FILL-COMPLETE",
    ]
    assert flag.conditions[0].values == ("Y", "N", "C", "P", "E", "B")
    split = model["ORRORH-SS-SPLIT-SHIP-FLAG"]
    assert [item.name for item in split.conditions] == [
        "ORRORH-SS-SPLIT-SHIP-VALID",
        "ORRORH-SS-SPLIT-ORDER",
        "ORRORH-SS-DO-NOT-SPLIT-ORDER",
    ]


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
    assert report.comment_records[0]["kind"] == "CL"
    assert report.comment_records[0]["fields"][0]["value"] == "CL"
    function = report.fields[0]
    assert function["name"] == "ORRORH-REQUEST-FUNCTION"
    assert function["value"] == "OR"
    assert function["conditions"][0]["name"] == "ORRORH-CREATE-ORDER"
    assert function["conditions"][0]["values"] == ["OR"]
    assert function["conditions"][0]["matched"] is True


def test_backorder_flag_conditions_match_current_value():
    xml = """
    <ns0:SSOrderEntryRequest>
        <ORRORH-REQUEST-FUNCTION>OR</ORRORH-REQUEST-FUNCTION>
        <ORRORH-BCK-BACKORDER-FLAG>Y</ORRORH-BCK-BACKORDER-FLAG>
        <ORRORH-SS-SPLIT-SHIP-FLAG>Y</ORRORH-SS-SPLIT-SHIP-FLAG>
    </ns0:SSOrderEntryRequest>
    """
    report = report_from_substation_xml(xml)
    flag = next(item for item in report.fields if item["name"] == "ORRORH-BCK-BACKORDER-FLAG")
    assert flag["value"] == "Y"
    by_name = {item["name"]: item for item in flag["conditions"]}
    assert by_name["ORRORH-BCK-ALLOW-BACKORDERS"]["matched"] is True
    assert by_name["ORRORH-BCK-NO-BACKORDERS"]["matched"] is False
    assert by_name["ORRORH-BCK-VALID-BO-FLAG"]["matched"] is True
    assert by_name["ORRORH-BCK-SHIP-COMPLETE"]["matched"] is False
    spaces = next(
        item for item in report.fields if item["name"] == "ORRORH-CUSTOMER-BR"
    )
    assert spaces["value"] == SPACES_VALUE
    assert "conditions" not in spaces


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


TIBCO_MESSAGE_P27951376 = (
    "<ns0:DateTimestamp>2026-10-02T01:00:43.463-07:00</ns0:DateTimestamp>"
    "<ns0:ServiceName>OrderUpdate_Service_root</ns0:ServiceName>"
    "<ns0:LogType>INFO</ns0:LogType>"
    "<ns0:CorrelationId>P279513762026-10-02T01:00:43.459-07:00</ns0:CorrelationId>"
    "<ns0:LogDescription>OrderCreateCallSubstationRequest</ns0:LogDescription>"
    "<ns0:CountryCode>MD</ns0:CountryCode>"
    "<ns0:JobID>2922719</ns0:JobID>"
    "<ns0:CustomerNumber>30-395650</ns0:CustomerNumber>"
    "<ns0:ServerName>uschleai2004</ns0:ServerName>"
    "<ns0:RequestLogPayload>Substation Request: {&#xD;"
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<ns0:SSOrderEntryRequest xmlns:ns0="http://www.ingrammicro.com/SSOrderEntryRequest">'
    "<ORRORH-PAYMENT-CODE/>"
    "<ORRORH-REQUEST-FUNCTION>OR</ORRORH-REQUEST-FUNCTION>"
    "<ORRORH-CUSTOMER-BR>30</ORRORH-CUSTOMER-BR>"
    "<ORRORH-CUSTOMER-NBR>395650</ORRORH-CUSTOMER-NBR>"
    "<ORRORH-COUNTRY-CODE>MD</ORRORH-COUNTRY-CODE>"
    "<ORRORH-CUST-TO-ING-PO-NBR>P27951376</ORRORH-CUST-TO-ING-PO-NBR>"
    "<ORRORH-CUST-TO-CUST-PO-NBR>P27951376</ORRORH-CUST-TO-CUST-PO-NBR>"
    "<ORRORD-DETAIL-ELEMENTS>HUGE DETAIL TRUNCATED BY DATADOG"
)


def _screenshot_substation_event() -> dict:
    """Datadog shape from PO P27951376: XML in message, no service facet."""
    return {
        "id": "upd-p27951376",
        "attributes": {
            "host": "uschleai2004",
            "message": TIBCO_MESSAGE_P27951376,
        },
    }


def test_substation_query_does_not_phrase_quote_po_and_description():
    query = build_substation_search_query(
        "P27951376",
        extra_terms=SUBSTATION_LOG_DESCRIPTION,
        service=None,
    )
    assert query == "P27951376 OrderCreateCallSubstationRequest"
    assert '"P27951376 OrderCreateCallSubstationRequest"' not in query


def test_substation_query_quotes_only_spaced_po():
    query = build_substation_search_query(
        "115669/2026 MI PB",
        extra_terms=SUBSTATION_LOG_DESCRIPTION,
        service=None,
    )
    assert query == '"115669 2026 MI PB" OrderCreateCallSubstationRequest'


def test_extract_substation_xml_without_close_tag():
    xml = extract_substation_xml(TIBCO_MESSAGE_P27951376)
    assert xml.startswith("<ns0:SSOrderEntryRequest")
    assert "</SSOrderEntryRequest>" not in xml
    assert "ORRORH-CUST-TO-CUST-PO-NBR>P27951376" in xml


def test_screenshot_shaped_log_builds_substation_report():
    event = _screenshot_substation_event()
    assert is_order_update_substation_event(event) is True
    xml = extract_substation_xml_from_event(event)
    assert "P27951376" in xml

    result = lookup_orrorh_from_events(
        v2_events=[],
        update_events=[event],
        order_number="P27951376",
    )
    assert result.source_log_id == "upd-p27951376"
    assert "ORRORH-REQUEST-FUNCTION = OR" in result.report
    assert "ORRORH-CUSTOMER-BR = 30" in result.report
    assert "ORRORH-CUST-TO-CUST-PO-NBR = P27951376" in result.report
    assert "ORRORH-CUST-TO-ING-PO-NBR = P27951376" in result.report


def test_customer_po_is_preferred_over_ingram_order_number():
    """Search 12948 must not attach Ingram order 12948 (60-SZ1840)."""
    ingram_event = {
        "id": "upd-ingram-12948",
        "attributes": {
            "service": "OrderUpdate_Service",
            "message": (
                "<ns0:ServiceName>OrderUpdate_Service_root</ns0:ServiceName>"
                "<ns0:LogDescription>OrderCreateCallSubstationRequest"
                "</ns0:LogDescription>"
                "<ns0:RequestLogPayload>Substation Request: "
                "<ns0:SSOrderEntryRequest>"
                "<ORRORH-REQUEST-FUNCTION>OR</ORRORH-REQUEST-FUNCTION>"
                "<ORRORH-CUSTOMER-BR>60</ORRORH-CUSTOMER-BR>"
                "<ORRORH-CUSTOMER-NBR>SZ1840</ORRORH-CUSTOMER-NBR>"
                "<ORRORH-INGRAM-ORDER-NBR>12948</ORRORH-INGRAM-ORDER-NBR>"
                "<ORRORD-DETAIL-ELEMENTS>\tPT</ORRORD-DETAIL-ELEMENTS>"
                "</ns0:SSOrderEntryRequest>"
            ),
        },
    }
    customer_event = {
        "id": "upd-customer-12948",
        "attributes": {
            "service": "OrderUpdate_Service",
            "message": (
                "<ns0:ServiceName>OrderUpdate_Service_root</ns0:ServiceName>"
                "<ns0:LogDescription>OrderCreateCallSubstationRequest"
                "</ns0:LogDescription>"
                "<ns0:RequestLogPayload>Substation Request: "
                "<ns0:SSOrderEntryRequest>"
                "<ORRORH-REQUEST-FUNCTION>OR</ORRORH-REQUEST-FUNCTION>"
                "<ORRORH-CUSTOMER-BR>41</ORRORH-CUSTOMER-BR>"
                "<ORRORH-CUSTOMER-NBR>008922</ORRORH-CUSTOMER-NBR>"
                "<ORRORH-CUST-TO-ING-PO-NBR>12948</ORRORH-CUST-TO-ING-PO-NBR>"
                "<ORRORD-DETAIL-ELEMENTS>\tOL                          001"
                "</ORRORD-DETAIL-ELEMENTS>"
                "</ns0:SSOrderEntryRequest>"
            ),
        },
    }
    xml, log_id = find_substation_xml(
        [ingram_event, customer_event],
        "12948",
    )
    assert log_id == "upd-customer-12948"
    assert "ORRORH-CUSTOMER-BR>41" in xml
    assert "SZ1840" not in xml

    result = lookup_orrorh_from_events(
        v2_events=[],
        update_events=[ingram_event, customer_event],
        order_number="12948",
    )
    assert result.source_log_id == "upd-customer-12948"
    assert "ORRORH-CUSTOMER-BR = 41" in result.report
    assert "ORRORH-CUSTOMER-NBR = 008922" in result.report
    assert "ORRORH-CUST-TO-ING-PO-NBR = 12948" in result.report
    assert result.line_records[0]["kind"] == "OL"


def test_ingram_order_number_alone_is_not_a_customer_po_match():
    event = {
        "id": "upd-ingram-only",
        "attributes": {
            "message": (
                "<ns0:LogDescription>OrderCreateCallSubstationRequest"
                "</ns0:LogDescription>"
                "<ns0:RequestLogPayload>Substation Request: "
                "<ns0:SSOrderEntryRequest>"
                "<ORRORH-REQUEST-FUNCTION>OR</ORRORH-REQUEST-FUNCTION>"
                "<ORRORH-CUSTOMER-BR>60</ORRORH-CUSTOMER-BR>"
                "<ORRORH-CUSTOMER-NBR>SZ1840</ORRORH-CUSTOMER-NBR>"
                "<ORRORH-INGRAM-ORDER-NBR>12948</ORRORH-INGRAM-ORDER-NBR>"
                "</ns0:SSOrderEntryRequest>"
            ),
        },
    }
    result = lookup_orrorh_from_events(
        v2_events=[],
        update_events=[event],
        order_number="12948",
    )
    assert result.xml == ""
    assert result.report == ""


def test_correlation_id_prefix_matches_when_xml_omits_po():
    event = {
        "id": "upd-cid",
        "attributes": {
            "message": (
                "<ns0:CorrelationId>P279513762026-10-02T01:00:43.459-07:00"
                "</ns0:CorrelationId>"
                "<ns0:LogDescription>OrderCreateCallSubstationRequest"
                "</ns0:LogDescription>"
                "<ns0:RequestLogPayload>Substation Request: "
                '<ns0:SSOrderEntryRequest>'
                "<ORRORH-REQUEST-FUNCTION>OR</ORRORH-REQUEST-FUNCTION>"
                "</ns0:SSOrderEntryRequest>"
            ),
        },
    }
    result = lookup_orrorh_from_events(
        v2_events=[],
        update_events=[event],
        order_number="P27951376",
    )
    assert result.source_log_id == "upd-cid"
    assert "ORRORH-REQUEST-FUNCTION = OR" in result.report


def test_fetch_orrorh_lookup_finds_screenshot_log(monkeypatch):
    event = _screenshot_substation_event()
    captured: list[str] = []

    def fake_search_logs(_client, params, should_stop=None):
        del should_stop
        query = params.filter.query
        captured.append(query)
        if "OrderCreate_v2" in query:
            return []
        if (
            "P27951376" in query
            and SUBSTATION_LOG_DESCRIPTION in query
            and not query.startswith('"P27951376 ')
        ):
            return [event]
        return []

    monkeypatch.setattr(
        "error_analysis.order_create.orrorh_report.search_logs",
        fake_search_logs,
    )
    result = fetch_orrorh_lookup(
        object(),  # type: ignore[arg-type]
        Settings(DD_API_KEY="test", DD_APP_KEY="test"),
        order_number="P27951376",
        from_time="2026-09-01T00:00:00Z",
        to_time="2026-10-02T12:00:00Z",
    )
    assert captured[0] == "P27951376 service:OrderCreate_v2*"
    assert (
        f"P27951376 service:{ORDER_UPDATE_SERVICE_FILTER} {SUBSTATION_LOG_DESCRIPTION}"
        in captured
    )
    assert all(
        '"P27951376 OrderCreateCallSubstationRequest"' not in query
        for query in captured
    )
    assert result.source_log_id == "upd-p27951376"
    assert "ORRORH-CUST-TO-CUST-PO-NBR = P27951376" in result.report


def test_fetch_orrorh_lookup_wildcard_when_po_only_in_correlation_id(monkeypatch):
    event = _screenshot_substation_event()
    captured: list[str] = []

    def fake_search_logs(_client, params, should_stop=None):
        del should_stop
        query = params.filter.query
        captured.append(query)
        if query.startswith("P27951376*") and SUBSTATION_LOG_DESCRIPTION in query:
            return [event]
        return []

    monkeypatch.setattr(
        "error_analysis.order_create.orrorh_report.search_logs",
        fake_search_logs,
    )
    result = fetch_orrorh_lookup(
        object(),  # type: ignore[arg-type]
        Settings(DD_API_KEY="test", DD_APP_KEY="test"),
        order_number="P27951376",
        from_time="2026-09-01T00:00:00Z",
        to_time="2026-10-02T12:00:00Z",
    )
    assert (
        f"P27951376* service:{ORDER_UPDATE_SERVICE_FILTER} {SUBSTATION_LOG_DESCRIPTION}"
        in captured
        or f"P27951376* {SUBSTATION_LOG_DESCRIPTION}" in captured
    )
    assert result.source_log_id == "upd-p27951376"
    assert "ORRORH-CUST-TO-ING-PO-NBR = P27951376" in result.report
