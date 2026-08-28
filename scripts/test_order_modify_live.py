#!/usr/bin/env python3
"""Live Datadog test: search OrderModify payload and build test-region curl."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Allow running from repo root without install quirks.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from error_analysis.config import get_settings
from error_analysis.datadog.client import DatadogClient
from error_analysis.datadog.errors import DatadogError
from error_analysis.datadog.fetch_request import (
    fetch_modify_request_records,
    fetch_request_records,
    resolve_service_filter,
)
from error_analysis.order_create.replay import default_search_window
from error_analysis.order_modify.modify_curl_builder import (
    OrderModifyCurlError,
    build_order_modify_curl_from_records,
    find_modify_body_records,
)


def _merge_records(*groups: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for group in groups:
        for record in group:
            log_id = str(record.get("log_id") or "")
            key = log_id or f"anon-{len(merged)}"
            if key not in merged:
                merged[key] = record
    return list(merged.values())


def main() -> int:
    po = (sys.argv[1] if len(sys.argv) > 1 else "PO26082807111243").strip()
    target = (sys.argv[2] if len(sys.argv) > 2 else "test").strip().lower()

    settings = get_settings()
    search_from, search_to = default_search_window(30)

    username = settings.order_modify_test_username
    password = settings.order_modify_test_password
    if target == "qa1":
        username = settings.order_modify_qa1_username
        password = settings.order_modify_qa1_password

    print(f"Customer order number: {po}")
    print(f"Target: {target}")
    print(f"Window: {search_from} -> {search_to}")
    print()

    try:
        with DatadogClient(settings) as client:
            modify_fetched = fetch_modify_request_records(
                client,
                settings,
                from_time=search_from,
                to_time=search_to,
                text=po,
                service=settings.default_modify_services,
            )
            create_fetched = fetch_request_records(
                client,
                settings,
                from_time=search_from,
                to_time=search_to,
                text=po,
                service=resolve_service_filter(settings),
            )
    except DatadogError as exc:
        print(f"Datadog error: {exc}", file=sys.stderr)
        return 1

    records = _merge_records(modify_fetched.records, create_fetched.records)
    modify_bodies = find_modify_body_records(records)

    print(f"Modify query: {modify_fetched.query}")
    print(f"Create query: {create_fetched.query}")
    print(f"Total merged records: {len(records)}")
    print(f"OrderModify body records: {len(modify_bodies)}")
    print()

    if not modify_bodies:
        print("No OrderModify_v6* RequestPayload found for this PO.", file=sys.stderr)
        if records:
            print("Other services found:", file=sys.stderr)
            for record in records[:10]:
                print(
                    f"  - {record.get('service')} @ {record.get('host')}",
                    file=sys.stderr,
                )
        return 2

    for idx, body in enumerate(modify_bodies):
        request = body.get("request") or {}
        print(f"[{idx}] service={body.get('service')} host={body.get('host')}")
        if isinstance(request, dict):
            print(f"    customerOrderNumber={request.get('customerOrderNumber')!r}")
            lines = request.get("lines")
            print(f"    lines={len(lines) if isinstance(lines, list) else 0}")
        print()

    if not username.strip():
        print("ORDER_MODIFY_TEST_USERNAME (or QA1) is not configured.", file=sys.stderr)
        return 3

    try:
        built = build_order_modify_curl_from_records(
            records,
            username=username,
            password=password,
            target=target,
            cookie=settings.order_create_cookie or None,
        )
    except OrderModifyCurlError as exc:
        print(f"Curl build failed: {exc}", file=sys.stderr)
        return 4

    out_path = ROOT / "results" / f"order-modify-{po}.curl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(built.curl + "\n", encoding="utf-8")

    print("Built Order Modify curl:")
    print(f"  URL: {built.url}")
    print(f"  Order id: {built.order_id}")
    print(f"  Saved: {out_path}")
    print()
    print(built.curl)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
