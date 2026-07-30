"""Dump all AsyncOrderCreate / OrderCreate_v6 log payload shapes for one PO."""
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

PO = sys.argv[1] if len(sys.argv) > 1 else "PO113046"
now = datetime.now(timezone.utc)
frm = (now - timedelta(days=14)).isoformat().replace("+00:00", "Z")
to = now.isoformat().replace("+00:00", "Z")
settings = get_settings()
hosts = sorted(PROD_ORDER_HOSTS)

query = build_checkout_query(
    search_text=PO,
    service=["AsyncOrderCreate", "OrderCreate_v6*", "OrderCreate_v2*"],
    host=hosts,
)
print("Query:", query)

out = []
with DatadogClient(settings) as client:
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
    n = 0
    for event in search_logs(client, params):
        n += 1
        attrs = event.get("attributes") or {}
        msg = str(attrs.get("message") or "")
        req = extract_hermes_request(event)
        resp = extract_hermes_response(event)
        entry = {
            "n": n,
            "service": attrs.get("service"),
            "host": attrs.get("host"),
            "timestamp": attrs.get("timestamp"),
            "msg_prefix": msg[:200].replace("\n", " "),
            "req_type": type(req).__name__ if req is not None else None,
            "resp_type": type(resp).__name__ if resp is not None else None,
            "req_keys": list(req.keys()) if isinstance(req, dict) else None,
            "resp_keys": list(resp.keys()) if isinstance(resp, dict) else None,
        }
        if isinstance(req, dict):
            entry["req"] = req
        if isinstance(resp, dict):
            entry["resp"] = resp
        # also peek nested attributes keys
        nested = attrs.get("attributes") or {}
        if isinstance(nested, dict):
            entry["attr_keys"] = sorted(nested.keys())[:40]
        out.append(entry)
        print(
            f"[{n}] {attrs.get('service')} | {entry['msg_prefix'][:120]!r} | "
            f"req_keys={entry['req_keys']} resp_keys={entry['resp_keys']}"
        )
        if n >= 30:
            break

path = ROOT / "results" / "order-type-ds-compare" / f"probe-{PO}.json"
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
print(f"Wrote {path} ({len(out)} events)")
