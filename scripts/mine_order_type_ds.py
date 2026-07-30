"""Mine SUCCESS OrderCreate v6 inbound requests for response orderType D vs S.

Flow:
1. Scan AsyncOrderCreate / OrderCreate_v6* on prod hosts for SUCCESS responses
   whose orders[].orderType is D (or S).
2. For each distinct customerOrderNumber, fetch the inbound portal v6 request
   (body with lines[], without orders[]).
3. Persist 10 samples each and compare field presence to infer D-mandatory fields.

Usage:
  .venv\\Scripts\\python scripts/mine_order_type_ds.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

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
from error_analysis.order_create.response_check import (
    classify_preamble,
    extract_preamble,
)

OUT_DIR = ROOT / "results" / "order-type-ds-compare"
TARGET_PER_TYPE = 10
MAX_RESPONSE_SCAN = 600
WINDOW_DAYS = 21


def _window(days: int = WINDOW_DAYS) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    return (
        start.isoformat().replace("+00:00", "Z"),
        now.isoformat().replace("+00:00", "Z"),
    )


def _hosts() -> list[str]:
    return sorted(PROD_ORDER_HOSTS)


def _services() -> list[str]:
    return ["AsyncOrderCreate", "OrderCreate_v6*", "OrderCreate_v2*"]


def _is_success_payload(payload: Any) -> bool:
    preamble = extract_preamble(payload)
    if preamble is not None:
        return classify_preamble(preamble) == "SUCCESS"
    if not isinstance(payload, dict):
        return False
    # REST-shaped success: orders with ingramOrderNumber and no hard failure
    orders = payload.get("orders")
    if isinstance(orders, list) and orders:
        for order in orders:
            if not isinstance(order, dict):
                continue
            if order.get("ingramOrderNumber"):
                errs = order.get("numberOfLinesWithError")
                if errs in (0, "0", None):
                    return True
    return False


def _order_types(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    orders = payload.get("orders")
    if not isinstance(orders, list):
        return []
    out: list[str] = []
    for order in orders:
        if isinstance(order, dict) and order.get("orderType"):
            out.append(str(order["orderType"]).strip().upper())
    return out


def _customer_po(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("customerOrderNumber") or "").strip()


def _is_inbound_v6(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if not isinstance(payload.get("lines"), list) or not payload["lines"]:
        return False
    # Response echo has orders[]; inbound request does not.
    if isinstance(payload.get("orders"), list):
        return False
    return bool(payload.get("customerOrderNumber"))


def _attr_map(attrs: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    if not isinstance(attrs, list):
        return out
    for item in attrs:
        if not isinstance(item, dict):
            continue
        name = str(
            item.get("attributeName") or item.get("attributename") or ""
        ).strip()
        if not name:
            continue
        value = item.get("attributeValue")
        if value is None:
            value = item.get("attributevalue")
        out[name] = "" if value is None else str(value).strip()
    return out


def _flatten_paths(obj: Any, prefix: str = "") -> set[str]:
    paths: set[str] = set()
    if isinstance(obj, dict):
        if not obj:
            if prefix:
                paths.add(prefix)
            return paths
        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else key
            if key in (
                "additionalAttributes",
                "vmfAdditionalAttributes",
                "productextendedspecs",
                "serviceextendedspecs",
                "vmfspecs",
            ) and isinstance(value, list):
                paths.add(path)
                for item in value:
                    if isinstance(item, dict):
                        name = str(
                            item.get("attributeName")
                            or item.get("attributename")
                            or ""
                        ).strip()
                        if name:
                            paths.add(f"{path}[{name}]")
                continue
            if isinstance(value, (dict, list)):
                child = _flatten_paths(value, path)
                paths |= child
                if not child and value not in ([], {}):
                    paths.add(path)
            else:
                if value is None:
                    continue
                if isinstance(value, str) and not value.strip():
                    continue
                paths.add(path)
    elif isinstance(obj, list):
        if not obj:
            if prefix:
                paths.add(prefix)
            return paths
        paths.add(prefix)
        for item in obj[:5]:
            paths |= _flatten_paths(item, f"{prefix}[]")
    return paths


def _search(
    client: DatadogClient,
    settings: Any,
    *,
    text: str,
    from_time: str,
    to_time: str,
    page_limit: int = 50,
):
    query = build_checkout_query(
        search_text=text,
        service=_services(),
        host=_hosts(),
    )
    params = LogSearchParams(
        filter=LogSearchFilter(
            query=query,
            from_time=from_time,
            to_time=to_time,
            storage_tier=settings.default_storage_tier,
        ),
        sort=settings.default_sort,
        page_limit=page_limit,
    )
    return query, search_logs(client, params)


def _find_inbound_for_po(
    client: DatadogClient,
    settings: Any,
    po: str,
    from_time: str,
    to_time: str,
) -> dict[str, Any] | None:
    _query, events = _search(
        client,
        settings,
        text=po,
        from_time=from_time,
        to_time=to_time,
        page_limit=50,
    )
    for event in events:
        req = extract_hermes_request(event)
        if not _is_inbound_v6(req):
            continue
        assert isinstance(req, dict)
        if str(req.get("customerOrderNumber") or "").strip().upper() != po.upper():
            continue
        attrs = event.get("attributes") or {}
        return {
            "customer_order_number": po,
            "timestamp": attrs.get("timestamp"),
            "service": attrs.get("service"),
            "host": attrs.get("host"),
            "log_id": event.get("id"),
            "is_portal_body": _is_portal_v6_body(req),
            "request": req,
        }
    return None


def _collect(
    client: DatadogClient,
    settings: Any,
    *,
    order_type: str,
    from_time: str,
    to_time: str,
    target: int = TARGET_PER_TYPE,
) -> list[dict[str, Any]]:
    text = f'resellerInfo "orderType":"{order_type}" SUCCESS'
    query, events = _search(
        client,
        settings,
        text=text,
        from_time=from_time,
        to_time=to_time,
        page_limit=100,
    )
    print(f"\n=== Collect orderType={order_type} ===")
    print(f"Query: {query}")

    candidate_pos: list[str] = []
    seen: set[str] = set()
    scanned = 0
    success_hits = 0

    for event in events:
        scanned += 1
        if scanned > MAX_RESPONSE_SCAN:
            break
        payload = extract_hermes_response(event) or extract_hermes_request(event)
        if not isinstance(payload, dict):
            continue
        ots = _order_types(payload)
        if order_type.upper() not in ots:
            continue
        if not _is_success_payload(payload):
            # Free-text SUCCESS matched the log; for REST echo accept ingramOrderNumber.
            if not (
                isinstance(payload.get("orders"), list)
                and any(
                    isinstance(o, dict) and o.get("ingramOrderNumber")
                    for o in payload["orders"]
                )
            ):
                continue
        success_hits += 1
        po = _customer_po(payload)
        if not po or po.upper() in seen:
            continue
        seen.add(po.upper())
        candidate_pos.append(po)
        if len(candidate_pos) >= target * 3:
            break

    print(
        f"  scanned={scanned} success_hits={success_hits} "
        f"unique_pos={len(candidate_pos)}"
    )

    samples: list[dict[str, Any]] = []
    for po in candidate_pos:
        if len(samples) >= target:
            break
        print(f"  fetching inbound for {po}…", flush=True)
        inbound = _find_inbound_for_po(client, settings, po, from_time, to_time)
        if inbound is None:
            print("    MISSING inbound lines[] request")
            continue
        inbound["response_order_type"] = order_type.upper()
        inbound["success_verified"] = True
        samples.append(inbound)
        print(
            f"    OK service={inbound['service']} "
            f"keys={list(inbound['request'].keys())[:8]}…"
        )
    return samples


def _presence_stats(samples: list[dict[str, Any]]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for sample in samples:
        counter.update(_flatten_paths(sample["request"]))
    return counter


def _compare(
    d_samples: list[dict[str, Any]],
    s_samples: list[dict[str, Any]],
) -> dict[str, Any]:
    d_stats = _presence_stats(d_samples)
    s_stats = _presence_stats(s_samples)
    n_d = max(len(d_samples), 1)
    n_s = max(len(s_samples), 1)
    rows = []
    for path in sorted(set(d_stats) | set(s_stats)):
        d_count = d_stats.get(path, 0)
        s_count = s_stats.get(path, 0)
        d_rate = d_count / n_d
        s_rate = s_count / n_s
        rows.append(
            {
                "path": path,
                "d_count": d_count,
                "d_rate": round(d_rate, 2),
                "s_count": s_count,
                "s_rate": round(s_rate, 2),
                "delta_d_minus_s": round(d_rate - s_rate, 2),
            }
        )

    d_characteristic = [
        r for r in rows if r["d_rate"] >= 0.8 and r["s_rate"] <= 0.3
    ]
    present_all_d = [r for r in rows if r["d_rate"] == 1.0]
    present_all_d_not_all_s = [
        r for r in rows if r["d_rate"] == 1.0 and r["s_rate"] < 1.0
    ]
    shared_always = [
        r for r in rows if r["d_rate"] == 1.0 and r["s_rate"] == 1.0
    ]
    d_characteristic.sort(key=lambda r: (-r["delta_d_minus_s"], r["path"]))
    present_all_d_not_all_s.sort(key=lambda r: (r["s_rate"], r["path"]))
    present_all_d.sort(key=lambda r: (-r["delta_d_minus_s"], r["path"]))

    return {
        "sample_counts": {"D": len(d_samples), "S": len(s_samples)},
        "d_characteristic_fields": d_characteristic,
        "present_in_all_d": present_all_d,
        "present_in_all_d_not_all_s": present_all_d_not_all_s,
        "shared_always_present": shared_always,
        "all_field_presence": rows,
    }


def _line_type_summary(samples: list[dict[str, Any]]) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    has_direct_ship_flags = 0
    for sample in samples:
        req = sample["request"]
        for line in req.get("lines") or []:
            if not isinstance(line, dict):
                continue
            lt = str(line.get("lineType") or "").strip() or "(blank)"
            counts[lt] += 1
            attrs = _attr_map(line.get("additionalAttributes"))
            for name, value in attrs.items():
                if name.lower() in ("isdirectship", "directship") and value.lower() in (
                    "true",
                    "y",
                    "yes",
                    "1",
                ):
                    has_direct_ship_flags += 1
        # header attrs
        for name, value in _attr_map(req.get("additionalAttributes")).items():
            if "directship" in name.lower() and value.lower() in (
                "true",
                "y",
                "yes",
                "1",
            ):
                has_direct_ship_flags += 1
    return {
        "lineType_counts": dict(counts),
        "direct_ship_flag_hits": has_direct_ship_flags,
    }


def main() -> int:
    settings = get_settings()
    from_time, to_time = _window()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with DatadogClient(settings) as client:
        d_samples = _collect(
            client,
            settings,
            order_type="D",
            from_time=from_time,
            to_time=to_time,
        )
        s_samples = _collect(
            client,
            settings,
            order_type="S",
            from_time=from_time,
            to_time=to_time,
        )

    (OUT_DIR / "d-samples.json").write_text(
        json.dumps(d_samples, indent=2, default=str, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (OUT_DIR / "s-samples.json").write_text(
        json.dumps(s_samples, indent=2, default=str, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    comparison = _compare(d_samples, s_samples)
    comparison["window"] = {"from": from_time, "to": to_time}
    comparison["d_orders"] = [s["customer_order_number"] for s in d_samples]
    comparison["s_orders"] = [s["customer_order_number"] for s in s_samples]
    comparison["d_line_summary"] = _line_type_summary(d_samples)
    comparison["s_line_summary"] = _line_type_summary(s_samples)

    # Candidate mandatory for D = present in all D samples
    comparison["candidate_mandatory_for_d"] = [
        r["path"] for r in comparison["present_in_all_d"]
    ]
    # Strong D differentiators
    comparison["likely_d_specific_vs_s"] = [
        r["path"] for r in comparison["d_characteristic_fields"]
    ]

    (OUT_DIR / "comparison.json").write_text(
        json.dumps(comparison, indent=2, default=str, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("\n========== SUMMARY ==========")
    print(f"D samples ({len(d_samples)}): {comparison['d_orders']}")
    print(f"S samples ({len(s_samples)}): {comparison['s_orders']}")
    print(f"D line summary: {comparison['d_line_summary']}")
    print(f"S line summary: {comparison['s_line_summary']}")
    print("\nD-characteristic (high D, low S):")
    for row in comparison["d_characteristic_fields"][:50]:
        print(
            f"  {row['path']}: D={row['d_rate']:.0%} S={row['s_rate']:.0%} "
            f"delta={row['delta_d_minus_s']:+.2f}"
        )
    print("\nPresent in ALL D but not all S:")
    for row in comparison["present_in_all_d_not_all_s"][:50]:
        print(f"  {row['path']}: D=100% S={row['s_rate']:.0%}")
    print(f"\nArtifacts: {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
