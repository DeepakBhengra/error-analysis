import pytest

from error_analysis.datadog.query_builder import (
    build_checkout_query,
    format_service_filter,
)


def test_search_text_is_free_text_not_correlation_id():
    query = build_checkout_query(search_text="bw0a101orlv", service=None, env=None)
    assert query == "bw0a101orlv"


def test_search_text_defaults_to_order_create_services():
    query = build_checkout_query(search_text="DEEPAKDDTEST1", env=None)
    assert (
        query
        == "DEEPAKDDTEST1 service:(AsyncOrderCreate OR OrderCreate_v6* OR OrderCreate_v2*)"
    )


def test_format_service_filter_multiple():
    assert (
        format_service_filter(["OrderCreate_v6", "OrderCreate_v2"])
        == "service:(OrderCreate_v6 OR OrderCreate_v2)"
    )


def test_correlation_id_with_filters():
    query = build_checkout_query(correlation_id="G0D82", env="uat")
    assert (
        query
        == "G0D82 service:(AsyncOrderCreate OR OrderCreate_v6* OR OrderCreate_v2*) env:uat"
    )


def test_build_query_job_id_only():
    query = build_checkout_query(job_id="JOB-123", env="uat")
    assert (
        query
        == "JOB-123 service:(AsyncOrderCreate OR OrderCreate_v6* OR OrderCreate_v2*) env:uat"
    )


def test_build_query_all_ids():
    query = build_checkout_query(
        correlation_id="G0D82",
        job_id="JOB-123",
        customer_po="PO-98765",
        env="prod",
    )
    assert (
        query
        == "G0D82 JOB-123 PO-98765 service:(AsyncOrderCreate OR OrderCreate_v6* OR OrderCreate_v2*) env:prod"
    )


def test_build_query_keeps_existing_quotes():
    query = build_checkout_query(correlation_id='"G0D82"', env="uat", service=None)
    assert query == '"G0D82" env:uat'


def test_build_query_quotes_terms_with_spaces():
    query = build_checkout_query(search_text="PO 98765", service=None, env=None)
    assert query == '"PO 98765"'


def test_build_query_normalizes_slash_in_customer_po():
    """Datadog tokenizes on '/', so keep slash POs searchable as a phrase."""
    query = build_checkout_query(
        search_text="115669/2026 MI PB",
        service=None,
        env=None,
    )
    assert query == '"115669 2026 MI PB"'


def test_build_query_normalizes_slash_without_spaces():
    query = build_checkout_query(
        search_text="115669/2026",
        service="OrderCreate_v2*",
        env=None,
    )
    assert query == '"115669 2026" service:OrderCreate_v2*'


def test_build_query_requires_at_least_one_id():
    with pytest.raises(ValueError, match="At least one"):
        build_checkout_query(env="uat")


def test_single_service_override():
    query = build_checkout_query(
        search_text="DEEPAKDDTEST1",
        service="OrderCreate_v6",
        env=None,
    )
    assert query == "DEEPAKDDTEST1 service:OrderCreate_v6"


def test_host_filter():
    query = build_checkout_query(
        search_text="OrderCreate_v6_0",
        service="OrderCreate_v6",
        host="uschileai2503",
        env=None,
    )
    assert query == (
        "OrderCreate_v6_0 service:OrderCreate_v6 host:uschileai2503"
    )


def test_multi_host_filter():
    query = build_checkout_query(
        search_text="ASYNCO1",
        service="AsyncOrderCreate",
        host=["uschileai1401", "uschileai1402", "uschileai1403", "uschileai1404"],
        env=None,
    )
    assert query == (
        "ASYNCO1 service:AsyncOrderCreate "
        "host:(uschileai1401 OR uschileai1402 OR uschileai1403 OR uschileai1404)"
    )


def test_host_filter_comma_string():
    query = build_checkout_query(
        search_text="ASYNCO1",
        service="AsyncOrderCreate",
        host="uschileai1401,uschileai1402",
        env=None,
    )
    assert query == (
        "ASYNCO1 service:AsyncOrderCreate host:(uschileai1401 OR uschileai1402)"
    )
