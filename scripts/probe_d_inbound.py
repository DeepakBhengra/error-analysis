"""Find SUCCESS D/S responses, then fetch the inbound v6 request bodies."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from error_analysis.config import get_settings
from error_analysis.datadog.client import DatadogClient
from error_analysis.datadog.models import LogSearchFilter, LogSearchParams
from error_analysis.datadog.query_builder import build_checkout_query
from error_analysis.datadog.search import search_logs
from error_analysis.extractors.hermes_request import (
    extract_hermes_request,
    extract_hermes_response,
)
from error_analysis.order_create.curl_builder import PROD_ORDER_HOSTS
from error_analysis.order_create.pair_mining import _is_portal_v6_body

now = datetime.now(timezone.utc)
frm = (now - timedelta(days=7)).isoformat().replace("+00:00", "Z")
to = now.isoformat().replace("+00:00", "Z")
settings = get_settings()
hosts = sorted(PROD_ORDER_HOSTS)


def order_types_from(payload):
    found = []
    if not isinstance(payload, dict):
        return found
    orders = payload.get("orders")
    if isinstance(orders, list):
        for o in orders:
            if isinstance(o, dict) and o.get("orderType"):
                found.append(str(o["orderType"]).strip().upper())
    return found


def find_inbound_request(client, po: str):
    """Search for portal-style inbound request (has lines[], not orders[])."""
    query = build_checkout_query(
        search_text=f'{po} resellerInfo lines',
        service=["OrderCreate_v6*", "AsyncOrderCreate"],
        host=hosts,
    )
    params = LogSearchParams(
        filter=LogSearchFilter(
            query=query,
            from_time=frm,
            to_time=to,
            storage_tier=settings.default_storage_tier,
        ),
        sort="-timestamp",
        page_limit=25,
    )
    for event in search_logs(client, params):
        req = extract_hermes_request(event)
        if not isinstance(req, dict):
            continue
        if req.get("customerOrderNumber", "").strip().upper() != po.upper():
            # free-text may match substring
            if po.upper() not in json.dumps(req).upper():
                continue
        # Prefer true inbound: has lines, no orders (response shape)
        has_lines = isinstance(req.get("lines"), list) and req["lines"]
        has_orders = isinstance(req.get("orders"), list)
        attrs = event.get("attributes") or {}
        if has_lines and not has_orders:
            return {
                "shape": "inbound_lines",
                "service": attrs.get("service"),
                "host": attrs.get("host"),
                "keys": list(req.keys()),
                "request": req,
                "is_portal": _is_portal_v6_body(req),
            }
        if has_lines:
            return {
                "shape": "has_lines_and_orders",
                "service": attrs.get("service"),
                "host": attrs.get("host"),
                "keys": list(req.keys()),
                "request": req,
                "is_portal": _is_portal_v6_body(req),
            }
    return None


with DatadogClient(settings) as client:
    # Collect a few SUCCESS D response POs
    query = build_checkout_query(
        search_text='resellerInfo "orderType":"D" SUCCESS',
        service=["AsyncOrderCreate", "OrderCreate_v6*"],
        host=hosts,
    )
    print("Response query:", query)
    params = LogSearchParams(
        filter=LogSearchFilter(
            query=query,
            from_time=frm,
            to_time=to,
            storage_tier=settings.default_storage_tier,
        ),
        sort="-timestamp",
        page_limit=50,
    )
    seen = set()
    count = 0
    for event in search_logs(client, params):
        payload = extract_hermes_request(event) or extract_hermes_response(event)
        if not isinstance(payload, dict):
            continue
        ots = order_types_from(payload)
        if "D" not in ots:
            continue
        po = str(payload.get("customerOrderNumber") or "").strip()
        if not po or po.upper() in seen:
            continue
        seen.add(po.upper())
        count += 1
        print(f"\n=== D response PO={po!r} orderTypes={ots}")
        inbound = find_inbound_request(client, po)
        if inbound is None:
            print("  NO inbound lines[] request found")
        else:
            req = inbound["request"]
            print(
                f"  found shape={inbound['shape']} portal={inbound['is_portal']} "
                f"service={inbound['service']} keys={inbound['keys']}"
            )
            print("  request snippet:")
            print(json.dumps(req, indent=2, default=str)[:2000])
        if count >= 3:
            break
