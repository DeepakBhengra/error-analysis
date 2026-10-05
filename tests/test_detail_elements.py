"""ORRORD-DETAIL-ELEMENTS positional parse against ORRORC / ORRORL."""

from pathlib import Path

from error_analysis.order_create.copybook_layout import (
    load_pic_copybook,
    pic_storage_length,
)
from error_analysis.order_create.detail_elements import (
    DETAIL_RECORD_LENGTH,
    extract_detail_elements,
    first_detail_record_start,
    parse_detail_element_records,
    parse_detail_elements_from_xml,
    split_detail_records,
)
from error_analysis.order_create.orrorh_report import report_from_substation_xml

SAMPLE_XML = (
    Path(__file__).resolve().parent / "fixtures" / "substation_detail_elements.xml"
).read_text(encoding="utf-8")


def _record(prefix: str) -> str:
    return (prefix + (" " * DETAIL_RECORD_LENGTH))[:DETAIL_RECORD_LENGTH]


def test_pic_storage_length():
    assert pic_storage_length("X(02)") == 2
    assert pic_storage_length("X(039).") == 39
    assert pic_storage_length("X(1)") == 1
    assert pic_storage_length("9(13)V9(4)") == 17
    assert pic_storage_length("9(13)V9(04)") == 17
    assert pic_storage_length("9(15)V9(2)") == 17
    assert pic_storage_length("9(09)") == 9


def test_orrorc_layout_starts_at_request_function():
    fields = load_pic_copybook("ORRORC", "ORRORC-REQUEST-FUNCTION")
    names = [field.name for field in fields if not field.skip]
    assert names[0] == "ORRORC-REQUEST-FUNCTION"
    assert names[1] == "ORRORC-RECORD-ID"
    assert "ORRORC-COMMENT" in names
    assert "FILLER" not in names
    assert sum(field.length for field in fields) < DETAIL_RECORD_LENGTH
    record_id = next(field for field in fields if field.name == "ORRORC-RECORD-ID")
    assert [item.name for item in record_id.conditions] == [
        "ORRORC-CONFIGURATION-COMMENT",
        "ORRORC-ORDER-COMMENT",
        "ORRORC-DYNAMIC-MESSAGE",
        "ORRORC-ADDITIONAL-DESCRIPT",
    ]


def test_orrorl_layout_starts_at_request_function():
    fields = load_pic_copybook("ORRORL", "ORRORL-REQUEST-FUNCTION")
    names = [field.name for field in fields if not field.skip]
    assert names[0] == "ORRORL-REQUEST-FUNCTION"
    assert "ORRORL-ING-PART-NBR" in names
    assert "ORRORL-QTY-ORDERED" in names
    assert all("FILLER" not in name for name in names)


def test_synthetic_cl_ec_ol_records_map_like_header():
    detail = (
        _record("CLORC" + (" " * 32) + "HEADER")
        + _record("ECDES" + (" " * 32) + "PLEASE ENSURE VENDOR IS AWARE OF NB")
        + _record("OL" + (" " * 26) + "001" + (" " * 15) + "09WQ36      0000001")
    )
    comments, lines = parse_detail_element_records(detail)
    assert [item["kind"] for item in comments] == ["CL", "EC"]
    first = {item["name"]: item["value"] for item in comments[0]["fields"]}
    second = {item["name"]: item["value"] for item in comments[1]["fields"]}
    line = {item["name"]: item["value"] for item in lines[0]["fields"]}
    assert first["ORRORC-REQUEST-FUNCTION"] == "CL"
    assert first["ORRORC-RECORD-ID"] == "ORC"
    assert first["ORRORC-COMMENT"] == "HEADER"
    assert second["ORRORC-REQUEST-FUNCTION"] == "EC"
    assert second["ORRORC-RECORD-ID"] == "DES"
    assert second["ORRORC-COMMENT"] == "PLEASE ENSURE VENDOR IS AWARE OF NB"
    assert line["ORRORL-REQUEST-FUNCTION"] == "OL"
    assert line["ORRORL-CUST-LINE-NBR"] == "001"
    assert line["ORRORL-ING-PART-NBR"] == "09WQ36"
    assert line["ORRORL-QTY-ORDERED"] == "0000001"
    assert comments[0]["report"].startswith("1. ORRORC-REQUEST-FUNCTION = CL")


def test_split_detail_records_are_1980_from_first_cl():
    detail = extract_detail_elements(SAMPLE_XML)
    records = split_detail_records(detail)
    kinds = [kind for kind, _chunk in records]
    assert kinds[0] == "CL"
    assert kinds.count("EC") == 8
    assert kinds.count("OL") == 1
    assert all(len(chunk) == DETAIL_RECORD_LENGTH for _kind, chunk in records if _kind != "PT")


def test_comment_and_line_records_from_sample_xml():
    comments, lines = parse_detail_elements_from_xml(SAMPLE_XML)
    assert len(comments) == 9
    assert comments[0]["kind"] == "CL"
    first = {item["name"]: item for item in comments[0]["fields"]}
    assert first["ORRORC-REQUEST-FUNCTION"]["value"] == "CL"
    assert first["ORRORC-RECORD-ID"]["value"] == "ORC"
    assert first["ORRORC-COMMENT"]["value"] == "HEADER"
    orc = first["ORRORC-RECORD-ID"]["conditions"]
    by_name = {item["name"]: item for item in orc}
    assert by_name["ORRORC-ORDER-COMMENT"]["matched"] is True
    assert by_name["ORRORC-ADDITIONAL-DESCRIPT"]["matched"] is False

    second = {item["name"]: item for item in comments[1]["fields"]}
    assert second["ORRORC-REQUEST-FUNCTION"]["value"] == "EC"
    assert second["ORRORC-RECORD-ID"]["value"] == "DES"
    assert second["ORRORC-COMMENT"]["value"] == "PLEASE ENSURE VENDOR IS AWARE OF NB"
    last_comment = {item["name"]: item for item in comments[-1]["fields"]}
    assert last_comment["ORRORC-COMMENT"]["value"] == "MAZON"

    assert len(lines) == 1
    line = {item["name"]: item for item in lines[0]["fields"]}
    assert line["ORRORL-REQUEST-FUNCTION"]["value"] == "OL"
    assert line["ORRORL-CUST-LINE-NBR"]["value"] == "001"
    assert line["ORRORL-ING-PART-NBR"]["value"] == "09WQ36"
    assert line["ORRORL-QTY-ORDERED"]["value"] == "0000001"


def test_ol_first_payload_without_cl_parses_line():
    """PO 12948-style Substation detail starts at OL, not CL."""
    detail = "\t" + _record(
        "OL" + (" " * 26) + "001" + (" " * 15) + "80Q65499    0000001"
    )
    assert first_detail_record_start(detail) == 1
    comments, lines = parse_detail_element_records(detail)
    assert comments == []
    assert len(lines) == 1
    line = {item["name"]: item["value"] for item in lines[0]["fields"]}
    assert line["ORRORL-REQUEST-FUNCTION"] == "OL"
    assert line["ORRORL-CUST-LINE-NBR"] == "001"
    assert line["ORRORL-ING-PART-NBR"] == "80Q65499"
    assert line["ORRORL-QTY-ORDERED"] == "0000001"


def test_ol_first_xml_does_not_treat_incl_as_cl_start():
    """Letters CL inside a later field must not become the record start."""
    body = _record(
        "OL" + (" " * 26) + "001" + (" " * 15) + "80Q65499    0000001"
    )
    # INCL contains the letters CL; a raw find("CL") would start there and miss OL.
    poisoned = "  INCL  " + body
    assert first_detail_record_start(poisoned) == poisoned.find("OL")
    comments, lines = parse_detail_element_records(poisoned)
    assert comments == []
    assert lines[0]["kind"] == "OL"
    xml = (
        "<ns0:SSOrderEntryRequest>"
        "<ORRORH-REQUEST-FUNCTION>OR</ORRORH-REQUEST-FUNCTION>"
        "<ORRORH-CONFIGURATION-FLAG>Y</ORRORH-CONFIGURATION-FLAG>"
        f"<ORRORD-DETAIL-ELEMENTS>\t{body}PT</ORRORD-DETAIL-ELEMENTS>"
        "</ns0:SSOrderEntryRequest>"
    )
    result = report_from_substation_xml(xml)
    assert result.comment_records == []
    assert result.line_records[0]["fields"][0]["value"] == "OL"
    by_name = {item["name"]: item["value"] for item in result.line_records[0]["fields"]}
    assert by_name["ORRORL-ING-PART-NBR"] == "80Q65499"


def test_report_from_substation_xml_includes_detail_tabs():
    result = report_from_substation_xml(SAMPLE_XML)
    assert result.report.startswith("1. ORRORH-REQUEST-FUNCTION = OR")
    assert result.comment_records[0]["fields"][0]["value"] == "CL"
    assert result.line_records[0]["fields"][0]["value"] == "OL"
    assert "ORRORD-DETAIL-ELEMENTS" not in result.report
