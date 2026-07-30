from __future__ import annotations

import json
from pathlib import Path

from error_analysis.extractors.request_log_payload import extract_job_id
from error_analysis.order_create.pair_mining import (
    compare_pair,
    load_pairs,
    run_report,
)
from error_analysis.order_create.v2_to_v6 import convert_v2_to_v6


def test_extract_job_id_from_xml_message() -> None:
    event = {
        "id": "1",
        "attributes": {
            "message": (
                "<pfx5:LogPayload>"
                "<pfx5:ServiceName>OrderCreate_v6_0</pfx5:ServiceName>"
                "<pfx5:JobID>JOB-ABC-123</pfx5:JobID>"
                "<pfx5:CorrelationID>CORR-999</pfx5:CorrelationID>"
                '"RequestLogPayload":{"customerOrderNumber":"X"}'
                "</pfx5:LogPayload>"
            )
        },
    }
    assert extract_job_id(event) == "JOB-ABC-123"
    from error_analysis.extractors.request_log_payload import extract_correlation_id

    assert extract_correlation_id(event) == "CORR-999"


def test_extract_job_id_from_attributes() -> None:
    event = {
        "id": "1",
        "attributes": {
            "attributes": {"JobID": " nested-job "},
            "message": "no xml job here",
        },
    }
    assert extract_job_id(event) == "nested-job"


def test_extract_job_id_missing() -> None:
    assert extract_job_id({"attributes": {"message": "hello"}}) is None


def test_compare_pair_marks_enrichment_and_rule_gaps() -> None:
    v2 = {
        "ordercreaterequest": {
            "ordercreatedetails": {
                "customerponumber": "PO1",
                "billtosuffix": "000",
                "creditcarddetails": {},
                "lines": [
                    {
                        "linetype": "P",
                        "linenumber": "001",
                        "ingrampartnumber": "ABC",
                        "quantity": 1.0,
                        "enduser": {},
                    }
                ],
                "extendedspecs": [
                    {
                        "attributename": "rslrCTACEmailInd",
                        "attributevalue": "a@b.com",
                    },
                    {
                        "attributename": "resellerctacemail",
                        "attributevalue": "a@b.com",
                    },
                    {
                        "attributename": "duplicatecustomerordernumbervalidate",
                        "attributevalue": "ALLOW",
                    },
                ],
            }
        }
    }
    converted = convert_v2_to_v6(v2)
    actual = json.loads(json.dumps(converted))
    actual.setdefault("resellerInfo", {})["companyName"] = "ENRICHED CO"
    actual["extraTopLevel"] = "should-be-rule-gap-missing"

    result = compare_pair(v2, actual, job_id="j1")
    enrichment_paths = {d.path for d in result.enrichment_diffs}
    rule_paths = {d.path for d in result.rule_gaps}
    assert "resellerInfo.companyName" in enrichment_paths
    assert "extraTopLevel" in rule_paths
    assert result.ok is False


def test_compare_pair_attr_list_order_insensitive(tmp_path: Path) -> None:
    v2 = {
        "ordercreaterequest": {
            "ordercreatedetails": {
                "customerponumber": "PO2",
                "lines": [],
                "extendedspecs": [
                    {"attributename": "basketid", "attributevalue": "B1"},
                    {"attributename": "userid", "attributevalue": "U1"},
                    {
                        "attributename": "duplicatecustomerordernumbervalidate",
                        "attributevalue": "ALLOW",
                    },
                ],
            }
        }
    }
    converted = convert_v2_to_v6(v2)
    actual = json.loads(json.dumps(converted))
    # Reverse attribute order — should still match.
    actual["additionalAttributes"] = list(
        reversed(actual["additionalAttributes"])
    )
    result = compare_pair(v2, actual, job_id="j2")
    assert result.ok


def test_run_report_writes_file(tmp_path: Path) -> None:
    v2 = {
        "ordercreaterequest": {
            "ordercreatedetails": {
                "customerponumber": "PO3",
                "lines": [],
                "extendedspecs": [],
            }
        }
    }
    v6 = convert_v2_to_v6(v2)
    pair_path = tmp_path / "job1.json"
    pair_path.write_text(
        json.dumps(
            {"job_id": "job1", "v2_request": v2, "v6_request": v6},
            indent=2,
        ),
        encoding="utf-8",
    )
    report_path = tmp_path / "report.json"
    report = run_report(tmp_path, out_path=report_path)
    assert report["pair_count"] == 1
    assert report["ok_count"] == 1
    assert report_path.exists()
    assert load_pairs(tmp_path)[0]["job_id"] == "job1"
