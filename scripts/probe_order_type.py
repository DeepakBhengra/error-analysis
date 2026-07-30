"""Quick probe: how orderType D/S appear in prod OrderCreate_v6 logs."""
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

now = datetime.now(timezone.utc)
frm = (now - timedelta(days=14)).isoformat().replace("+00:00", "Z")
to = now.isoformat().replace("+00:00", "Z")

queries = [
    'resellerInfo "orderType":"D"',
    '"orderType":"D" SUCCESS',
    '"orderType": "D"',
    'additionalAttributes orderType D resellerInfo',
]

settings = get_settings()
hosts = sorted(PROD_ORDER_HOSTS)

with DatadogClient(settings) as client:
    for text in queries:
        query = build_checkout_query(
            search_text=text,
            service=["OrderCreate_v6*", "AsyncOrderCreate"],
            host=hosts,
        )
        print("\n====", text)
        print("Q:", query)
        params = LogSearchParams(
            filter=LogSearchFilter(
                query=query,
                from_time=frm,
                to_time=to,
                storage_tier=settings.default_storage_tier,
            ),
            sort="-timestamp",
            page_limit=10,
        )
        n = 0
        for event in search_logs(client, params):
            n += 1
            attrs = event.get("attributes") or {}
            msg = str(attrs.get("message") or "")[:160].replace("\n", " ")
            req = extract_hermes_request(event)
            resp = extract_hermes_response(event)
            print(
                f"  [{n}] service={attrs.get('service')} host={attrs.get('host')} "
                f"req={'Y' if req else 'N'} resp={'Y' if resp else 'N'} msg={msg!r}"
            )
            if isinstance(req, dict):
                keys = list(req.keys())[:12]
                print(f"       req_keys={keys}")
                # dump orderType locations
                blob = json.dumps(req)
                if "orderType" in blob:
                    idx = blob.find("orderType")
                    print(f"       req_snip={blob[max(0,idx-40):idx+60]}")
            if isinstance(resp, dict):
                blob = json.dumps(resp)
                if "orderType" in blob:
                    idx = blob.find("orderType")
                    print(f"       resp_snip={blob[max(0,idx-40):idx+60]}")
            if n >= 5:
                break
        print(f"  total_shown={n}")
