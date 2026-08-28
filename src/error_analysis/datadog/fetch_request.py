from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from error_analysis.config import Settings
from error_analysis.datadog.client import DatadogClient
from error_analysis.datadog.models import LogSearchFilter, LogSearchParams
from error_analysis.datadog.query_builder import build_checkout_query
from error_analysis.datadog.search import search_logs
from error_analysis.extractors.hermes_request import (
    build_fetch_request_record,
    extract_log_payloads,
)
from error_analysis.extractors.modify_request import extract_modify_request
from error_analysis.extractors.request_log_payload import extract_correlation_id


@dataclass(frozen=True)
class FetchRequestResult:
    records: list[dict[str, Any]]
    query: str
    total_logs: int
    missing_payload: int
    request_count: int
    response_count: int


def resolve_service_filter(
    settings: Settings,
    *,
    service: str | None = None,
    no_service_filter: bool = False,
) -> str | list[str] | None:
    if no_service_filter:
        return None
    if service and service.strip():
        return service.strip()
    return settings.default_services


def fetch_request_records(
    client: DatadogClient,
    settings: Settings,
    *,
    from_time: str,
    to_time: str,
    text: str | None = None,
    correlation_id: str | None = None,
    job_id: str | None = None,
    customer_po: str | None = None,
    env: str | None = None,
    service: str | list[str] | None = None,
    limit: int | None = None,
) -> FetchRequestResult:
    """Search Datadog and extract Hermes request/response records."""
    query = build_checkout_query(
        search_text=text,
        correlation_id=correlation_id,
        job_id=job_id,
        customer_po=customer_po,
        env=env,
        service=service,
    )
    params = LogSearchParams(
        filter=LogSearchFilter(
            query=query,
            **{"from": from_time, "to": to_time},
            storage_tier=settings.default_storage_tier,
        ),
        sort=settings.default_sort,
        page_limit=limit or settings.default_page_limit,
    )

    results: list[dict[str, Any]] = []
    missing_payload = 0
    total_logs = 0
    request_count = 0
    response_count = 0

    for event in search_logs(client, params):
        total_logs += 1
        request, response = extract_log_payloads(event)
        if request is None and response is None:
            missing_payload += 1
            continue
        if request is not None:
            request_count += 1
        if response is not None:
            response_count += 1
        results.append(
            build_fetch_request_record(
                event,
                request=request,
                response=response,
                search_text=text,
                # Keep the CorrelationId from the log's XML wrapper (e.g.
                # <pfx5:CorrelationId>) so curl building can fall back to it
                # for the IM-CorrelationID header.
                correlation_id=correlation_id or extract_correlation_id(event),
                job_id=job_id,
                customer_po=customer_po,
                env=env or "",
            )
        )

    return FetchRequestResult(
        records=results,
        query=query,
        total_logs=total_logs,
        missing_payload=missing_payload,
        request_count=request_count,
        response_count=response_count,
    )


def fetch_modify_request_records(
    client: DatadogClient,
    settings: Settings,
    *,
    from_time: str,
    to_time: str,
    text: str | None = None,
    correlation_id: str | None = None,
    job_id: str | None = None,
    customer_po: str | None = None,
    env: str | None = None,
    service: str | list[str] | None = None,
    limit: int | None = None,
) -> FetchRequestResult:
    """Search Datadog and extract Order Modify RequestPayload records."""
    modify_service = service
    if modify_service is None:
        modify_service = settings.order_modify_services

    query = build_checkout_query(
        search_text=text,
        correlation_id=correlation_id,
        job_id=job_id,
        customer_po=customer_po,
        env=env,
        service=modify_service,
    )
    params = LogSearchParams(
        filter=LogSearchFilter(
            query=query,
            **{"from": from_time, "to": to_time},
            storage_tier=settings.default_storage_tier,
        ),
        sort=settings.default_sort,
        page_limit=limit or settings.default_page_limit,
    )

    results: list[dict[str, Any]] = []
    missing_payload = 0
    total_logs = 0
    request_count = 0
    response_count = 0

    for event in search_logs(client, params):
        total_logs += 1
        request = extract_modify_request(event)
        _, response = extract_log_payloads(event)
        if request is None and response is None:
            missing_payload += 1
            continue
        if request is not None:
            request_count += 1
        if response is not None:
            response_count += 1
        results.append(
            build_fetch_request_record(
                event,
                request=request,
                response=response,
                search_text=text,
                correlation_id=correlation_id or extract_correlation_id(event),
                job_id=job_id,
                customer_po=customer_po,
                env=env or "",
            )
        )

    return FetchRequestResult(
        records=results,
        query=query,
        total_logs=total_logs,
        missing_payload=missing_payload,
        request_count=request_count,
        response_count=response_count,
    )
