"""Regression tests for Datadog fetch_request helpers."""

from __future__ import annotations

from error_analysis.datadog.fetch_request import (
    FetchRequestResult,
    fetch_modify_request_records,
    fetch_request_records,
)


def test_fetch_request_records_returns_results_list(monkeypatch):
    """Ensure fetch_request_records returns extracted records (not NameError)."""

    class FakeClient:
        pass

    def fake_search_logs(_client, _params, should_stop=None):
        yield {
            "id": "log-1",
            "attributes": {
                "service": "OrderCreate_v6",
                "host": "host1",
                "message": (
                    '{"RequestLogPayload":{"customerOrderNumber":"PO1",'
                    '"lines":[],"resellerInfo":{}}}'
                ),
            },
        }

    monkeypatch.setattr(
        "error_analysis.datadog.fetch_request.search_logs",
        fake_search_logs,
    )

    class FakeSettings:
        default_storage_tier = "indexes"
        default_sort = "-timestamp"
        default_page_limit = 50

    result = fetch_request_records(
        FakeClient(),
        FakeSettings(),  # type: ignore[arg-type]
        from_time="2026-01-01T00:00:00Z",
        to_time="2026-01-02T00:00:00Z",
        text="PO1",
        service=["OrderCreate_v6*"],
    )

    assert isinstance(result, FetchRequestResult)
    assert len(result.records) == 1
    assert result.records[0]["log_id"] == "log-1"


def test_fetch_modify_request_records_stops_early(monkeypatch):
    pages = [
        {
            "id": "log-1",
            "attributes": {
                "service": "OrderModify_v6_0",
                "host": "host1",
                "message": (
                    "OrderNumber:- 29-44694-11RequestPayload:- "
                    '{"customerOrderNumber":"PO1","lines":[]}'
                ),
            },
        },
        {
            "id": "log-2",
            "attributes": {
                "service": "OrderModify_v6_0",
                "host": "host1",
                "message": "OrderNumber:- 29-99999-11RequestPayload:- {}",
            },
        },
    ]
    calls = {"count": 0}

    def fake_search_logs(_client, _params, should_stop=None):
        for event in pages:
            calls["count"] += 1
            yield event
            if should_stop is not None and should_stop(True):
                return

    monkeypatch.setattr(
        "error_analysis.datadog.fetch_request.search_logs",
        fake_search_logs,
    )

    class FakeSettings:
        default_storage_tier = "indexes"
        default_sort = "-timestamp"
        default_page_limit = 50
        order_modify_services = ["OrderModify_v6*"]

    result = fetch_modify_request_records(
        object(),
        FakeSettings(),  # type: ignore[arg-type]
        from_time="2026-01-01T00:00:00Z",
        to_time="2026-01-02T00:00:00Z",
        text="PO1",
        early_stop_index=0,
    )

    assert calls["count"] == 1
    assert len(result.records) == 1
