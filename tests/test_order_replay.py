from pathlib import Path

from typer.testing import CliRunner

from error_analysis.cli import app
from error_analysis.order_create.order_number import (
    apply_order_number,
    bump_trailing_number,
    random_order_number,
    resolve_replay_order_number,
)
from error_analysis.order_create.replay import post_order_create
from error_analysis.order_create.response_check import (
    build_error_report,
    build_result_payload,
    build_success_summary,
    classify_preamble,
    find_response_check,
)

runner = CliRunner()


def test_bump_trailing_number():
    assert bump_trailing_number("DEEPAKDDTEST11") == "DEEPAKDDTEST12"
    assert bump_trailing_number("TEST011") == "TEST012"
    assert bump_trailing_number("TEST099") == "TEST100"
    assert bump_trailing_number("NODIGITS") == "NODIGITS1"


def test_random_order_number_uses_prefix():
    value = random_order_number(prefix="DEEPAKDDTEST11")
    assert value.startswith("DEEP")
    assert value != "DEEPAKDDTEST11"
    assert len(value) <= 20


def test_random_order_number_max_20_chars():
    value = random_order_number(prefix="VERYLONGCUSTOMERORDERPREFIX999")
    assert len(value) == 20
    assert value != "VERYLONGCUSTOMERORDERPREFIX999"


def test_random_order_number_does_not_echo_long_po():
    original = "MP-103923L10401876"
    value = random_order_number(prefix=original)
    assert len(value) <= 20
    assert value.startswith("MPL")
    assert "10401876" not in value
    assert value != original


def test_resolve_replay_order_number():
    assert resolve_replay_order_number("A10", explicit="CUSTOM99") == "CUSTOM99"
    assert resolve_replay_order_number("A10") == "A11"
    random_value = resolve_replay_order_number("A10", use_random=True)
    assert random_value.startswith("A")
    assert random_value != "A10"
    assert len(random_value) <= 20


def test_resolve_replay_clamps_one_up_to_20():
    # Appending "1" would exceed 20; result must still be clamped.
    original = "MP-103923L10401876EX"  # 20 chars, no trailing digits
    bumped = resolve_replay_order_number(original)
    assert len(bumped) <= 20
    assert bumped == "MP-103923L10401876EX1"[:20]


def test_apply_order_number():
    body = {
        "customerOrderNumber": "OLD1",
        "endCustomerOrderNumber": "OLD1",
        "notes": "keep",
    }
    updated = apply_order_number(body, "NEW2")
    assert updated["customerOrderNumber"] == "NEW2"
    assert updated["endCustomerOrderNumber"] == "NEW2"
    assert body["customerOrderNumber"] == "OLD1"
    assert updated["notes"] == "keep"


def test_classify_preamble_success():
    assert (
        classify_preamble(
            {
                "responsestatus": "SUCCESS",
                "statuscode": "200",
                "responsemessage": "SUCCESS",
                "errorcode": "",
            }
        )
        == "SUCCESS"
    )
    assert (
        classify_preamble(
            {
                "responsestatus": "SUCCESS",
                "statuscode": "200",
                "responsemessage": "SUCCESS",
            }
        )
        == "SUCCESS"
    )


def test_classify_preamble_failed():
    assert (
        classify_preamble(
            {
                "responsestatus": "FAILED",
                "statuscode": "EN",
                "responsemessage": "SKU-NOTFOUND    9Y7663AA",
            }
        )
        == "FAILED"
    )


def test_classify_preamble_unknown():
    assert (
        classify_preamble(
            {
                "responsestatus": "SUCCESS",
                "statuscode": "200",
                "responsemessage": "SUCCESS",
                "errorcode": "X",
            }
        )
        == "UNKNOWN"
    )


def test_find_response_check_prefers_failed():
    records = [
        {
            "log_id": "1",
            "ResponseLogPayload": {
                "responsepreamble": {
                    "responsestatus": "SUCCESS",
                    "statuscode": "200",
                    "responsemessage": "SUCCESS",
                }
            },
        },
        {
            "log_id": "2",
            "ResponseLogPayload": {
                "responsepreamble": {
                    "responsestatus": "FAILED",
                    "statuscode": "EN",
                    "responsemessage": "SKU-NOTFOUND",
                }
            },
        },
    ]
    check = find_response_check(records)
    assert check is not None
    assert check.outcome == "FAILED"
    assert check.statuscode == "EN"
    assert check.source_log_id == "2"


def test_build_error_report_shape():
    check = find_response_check(
        [
            {
                "log_id": "abc",
                "ResponseLogPayload": {
                    "responsepreamble": {
                        "responsestatus": "FAILED",
                        "statuscode": "EN",
                        "responsemessage": "SKU-NOTFOUND",
                        "errorcode": "",
                    }
                },
            }
        ]
    )
    assert check is not None
    report = build_error_report(
        customer_order_number="DEEPAKDDTEST13",
        check=check,
        http_status=200,
        original_customer_order_number="DEEPAKDDTEST12",
        source_search_text="DEEPAKDDTEST12",
    )
    assert report["sourceSearchText"] == "DEEPAKDDTEST12"
    assert report["originalCustomerOrderNumber"] == "DEEPAKDDTEST12"
    assert report["customerOrderNumber"] == "DEEPAKDDTEST13"
    assert report["outcome"] == "FAILED"
    assert report["statuscode"] == "EN"
    assert report["responsemessage"] == "SKU-NOTFOUND"
    assert report["errorcode"] == ""
    assert report["http_status"] == 200
    assert "fetched_at" in report
    assert report["ResponseLogPayload"]["responsepreamble"]["responsestatus"] == "FAILED"


def test_build_success_summary_shape():
    check = find_response_check(
        [
            {
                "log_id": "ok",
                "response": {
                    "responsepreamble": {
                        "responsestatus": "SUCCESS",
                        "statuscode": "200",
                        "responsemessage": "SUCCESS",
                        "errorcode": "",
                    }
                },
            }
        ]
    )
    assert check is not None
    summary = build_success_summary(
        customer_order_number="PO2",
        check=check,
        http_status=201,
        original_customer_order_number="PO1",
        source_search_text="PO1",
    )
    assert summary["outcome"] == "SUCCESS"
    assert summary["statuscode"] == "200"
    assert summary["responsemessage"] == "SUCCESS"
    assert summary["errorcode"] == ""
    assert summary["http_status"] == 201
    assert summary["sourceSearchText"] == "PO1"
    assert summary["originalCustomerOrderNumber"] == "PO1"


def test_build_result_payload_always_has_error_fields():
    payload = build_result_payload(
        outcome="FAILED",
        customer_order_number="N13",
        original_customer_order_number="N12",
        source_search_text="N12",
        statuscode="EN",
        responsemessage="SKU-NOTFOUND",
        errorcode="",
        http_status=200,
    )
    assert set(payload) >= {
        "sourceSearchText",
        "originalCustomerOrderNumber",
        "customerOrderNumber",
        "outcome",
        "statuscode",
        "responsemessage",
        "errorcode",
        "http_status",
        "fetched_at",
        "source_log_id",
    }


def test_post_order_create_sends_auth_and_json(httpx_mock):
    httpx_mock.add_response(
        method="POST",
        url="https://example.test/orders",
        json={"ok": True},
        status_code=201,
    )
    status, body = post_order_create(
        url="https://example.test/orders",
        headers={"IM-CountryCode": "US", "Content-Type": "application/json"},
        body={"customerOrderNumber": "T1"},
        username="user",
        password="pass",
    )
    assert status == 201
    assert body == {"ok": True}
    request = httpx_mock.get_request()
    assert request is not None
    assert request.headers["IM-CountryCode"] == "US"
    assert request.headers["Authorization"].startswith("Basic ")
    assert b'"customerOrderNumber":"T1"' in request.content


def test_find_response_check_none_when_missing():
    assert find_response_check([{"ResponseLogPayload": None}]) is None
    assert find_response_check([{"response": {"ordersummary": {}}}]) is None


def test_find_response_check_prefers_v6_response_formed_over_note_log():
    """PP006564049 scenario: a WY 'Address fixed' note record must not shadow
    the OrderCreate_v6_0 'OrderCreate Response formed' FAILED/EN response."""
    records = [
        {
            "log_id": "note",
            "service": "OrderCreate_v2_0",
            "host": "uschileai2503",
            "ResponseLogPayload": {
                "responsepreamble": {
                    "responsestatus": "SUCCESS",
                    "statuscode": "200",
                    "responsemessage": "SUCCESS",
                    "errorcode": "WY",
                }
            },
        },
        {
            "log_id": "v6",
            "service": "OrderCreate_v6_0",
            "host": "uschileai2503",
            "ResponseLogPayload": {
                "serviceresponse": True,
                "responsepreamble": {
                    "responsestatus": "FAILED",
                    "statuscode": "EN",
                    "responsemessage": "SKU-NOTFOUND    790R96",
                },
            },
        },
    ]
    check = find_response_check(records)
    assert check is not None
    assert check.outcome == "FAILED"
    assert check.statuscode == "EN"
    assert check.source_log_id == "v6"
    assert check.source_service == "OrderCreate_v6_0"


def test_find_response_check_v6_success_wins_over_v2_failure():
    records = [
        {
            "log_id": "v2",
            "service": "OrderCreate_v2_0",
            "ResponseLogPayload": {
                "responsepreamble": {
                    "responsestatus": "FAILED",
                    "statuscode": "D9",
                    "responsemessage": "some v2 error",
                }
            },
        },
        {
            "log_id": "v6",
            "service": "OrderCreate_v6_1",
            "ResponseLogPayload": {
                "responsepreamble": {
                    "responsestatus": "SUCCESS",
                    "statuscode": "200",
                    "responsemessage": "SUCCESS",
                }
            },
        },
    ]
    check = find_response_check(records)
    assert check is not None
    assert check.outcome == "SUCCESS"
    assert check.source_log_id == "v6"


def test_extract_globalorderid_serviceresponse_wrapper_and_fallbacks():
    from error_analysis.order_create.response_check import extract_globalorderid

    wrapped = {
        "serviceresponse": {
            "responsepreamble": {
                "responsestatus": "SUCCESS",
                "statuscode": "200",
                "responsemessage": "SUCCESS",
            },
            "ordersummary": {
                "customerponumber": "PO26071820472351",
                "ordercreateresponse": [
                    {"numberoflineswithsuccess": "1", "globalorderid": "41-PBWWJ"}
                ],
            },
        }
    }
    assert extract_globalorderid(wrapped) == "41-PBWWJ"

    # First entry blank, second carries the id.
    multi = {
        "ordersummary": {
            "ordercreateresponse": [
                {"globalorderid": ""},
                {"globalorderid": "41-XYZ12"},
            ]
        }
    }
    assert extract_globalorderid(multi) == "41-XYZ12"

    # invoicingsystemorderid fallback when globalorderid is absent.
    invoicing = {
        "ordersummary": {
            "ordercreateresponse": [{"invoicingsystemorderid": "41-PBWWJ"}]
        }
    }
    assert extract_globalorderid(invoicing) == "41-PBWWJ"

    # ordersummary-level fallback.
    summary_level = {"ordersummary": {"globalorderid": "41-TOP01"}}
    assert extract_globalorderid(summary_level) == "41-TOP01"

    assert extract_globalorderid({"ordersummary": {}}) == ""
    assert extract_globalorderid(None) == ""


def test_extract_globalorderid_rest_shapes():
    from error_analysis.order_create.response_check import extract_globalorderid

    # Public reseller v6 REST body.
    assert (
        extract_globalorderid(
            {"customerOrderNumber": "PO1", "orders": [{"ingramOrderNumber": "20-ABC12"}]}
        )
        == "20-ABC12"
    )
    # camelCase variants.
    assert extract_globalorderid({"globalOrderId": "41-CAMEL"}) == "41-CAMEL"
    assert (
        extract_globalorderid({"orderSummary": {"globalOrderId": "41-SUMM"}})
        == "41-SUMM"
    )


def test_find_globalorderid_in_records_scans_all_logs():
    from error_analysis.order_create.response_check import (
        find_globalorderid_in_records,
    )

    records = [
        # SUCCESS response log without ordersummary.
        {
            "log_id": "v6",
            "service": "OrderCreate_v6_0",
            "ResponseLogPayload": {
                "responsepreamble": {
                    "responsestatus": "SUCCESS",
                    "statuscode": "200",
                    "responsemessage": "SUCCESS",
                }
            },
        },
        # Sibling log carrying the ordersummary.
        {
            "log_id": "summary",
            "service": "OrderCreate_v6_0",
            "ResponseLogPayload": {
                "serviceresponse": {
                    "ordersummary": {
                        "ordercreateresponse": [{"globalorderid": "41-PBWWJ"}]
                    }
                }
            },
        },
    ]
    assert find_globalorderid_in_records(records) == "41-PBWWJ"
    assert find_globalorderid_in_records([]) == ""


def test_find_globalorderid_in_records_uses_v2_xml_impulse_number():
    from error_analysis.order_create.response_check import (
        find_globalorderid_in_records,
    )

    records = [
        {
            "log_id": "v2xml",
            "service": "OrderCreate_v2_0",
            "message": (
                "OrderCreate Response <pfx5:ServiceName>OrderCreate_v2_0"
                "</pfx5:ServiceName>"
                "<requestStatus>S</requestStatus>"
                "<returnCode>00</returnCode>"
                "<orderBranchNumber>41</orderBranchNumber>"
                "<orderNumber>PBWWJ</orderNumber>"
            ),
        }
    ]
    assert find_globalorderid_in_records(records) == "41-PBWWJ"


def test_find_response_check_handles_serviceresponse_wrapper():
    """v6 ResponseLogPayload wraps preamble+summary in 'serviceresponse'."""
    records = [
        {
            "log_id": "v6",
            "service": "OrderCreate_v6_0",
            "ResponseLogPayload": {
                "serviceresponse": {
                    "responsepreamble": {
                        "responsestatus": "SUCCESS",
                        "statuscode": "200",
                        "responsemessage": "SUCCESS",
                    },
                    "ordersummary": {
                        "ordercreateresponse": [{"globalorderid": "41-PBWWJ"}]
                    },
                }
            },
        }
    ]
    check = find_response_check(records)
    assert check is not None
    assert check.outcome == "SUCCESS"
    assert check.globalorderid == "41-PBWWJ"


def test_find_response_check_falls_back_when_no_v6_record():
    records = [
        {
            "log_id": "v2only",
            "service": "OrderCreate_v2_0",
            "ResponseLogPayload": {
                "responsepreamble": {
                    "responsestatus": "FAILED",
                    "statuscode": "D9",
                    "responsemessage": "v2 failure",
                }
            },
        },
    ]
    check = find_response_check(records)
    assert check is not None
    assert check.outcome == "FAILED"
    assert check.statuscode == "D9"
    assert check.source_log_id == "v2only"


def test_replay_order_requires_text_xor_from_file():
    result = runner.invoke(app, ["replay-order", "--out-dir", "results"])
    assert result.exit_code == 1
    assert "exactly one of --text or --from-file" in result.output

    result_both = runner.invoke(
        app,
        [
            "replay-order",
            "--text",
            "DEEPAKDDTEST12",
            "--from-file",
            "results/request.json",
            "--search-from",
            "2026-06-17T00:00:00Z",
            "--search-to",
            "2026-07-15T23:59:59Z",
        ],
    )
    assert result_both.exit_code == 1
    assert "exactly one of --text or --from-file" in result_both.output


def test_replay_order_text_requires_search_window(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DD_API_KEY", "k")
    monkeypatch.setenv("DD_APP_KEY", "a")
    result = runner.invoke(
        app,
        ["replay-order", "--text", "DEEPAKDDTEST12", "--out-dir", str(tmp_path)],
    )
    assert result.exit_code == 1
    assert "--search-from and --search-to are required" in result.output
