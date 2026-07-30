"""Analyze already-fetched samples + fetch more D/S inbound requests."""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
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

OUT_DIR = ROOT / "results" / "order-type-ds-compare"
TARGET = 10
MAX_SCAN = 1500


def window(days=30):
    now = datetime.now(timezone.utc)
    return (
        (now - timedelta(days=days)).isoformat().replace("+00:00", "Z"),
        now.isoformat().replace("+00:00", "Z"),
    )


def hosts():
    return sorted(PROD_ORDER_HOSTS)


def services():
    return ["AsyncOrderCreate", "OrderCreate_v6*", "OrderCreate_v2*"]


def order_types(payload):
    if not isinstance(payload, dict):
        return []
    orders = payload.get("orders")
    if not isinstance(orders, list):
        return []
    return [
        str(o.get("orderType") or "").strip().upper()
        for o in orders
        if isinstance(o, dict) and o.get("orderType")
    ]


def is_success_echo(payload):
    if not isinstance(payload, dict):
        return False
    orders = payload.get("orders")
    if not isinstance(orders, list) or not orders:
        return False
    for o in orders:
        if not isinstance(o, dict):
            continue
        if o.get("ingramOrderNumber"):
            errs = o.get("numberOfLinesWithError")
            if errs in (0, "0", None):
                return True
    return False


def is_inbound(payload):
    return (
        isinstance(payload, dict)
        and isinstance(payload.get("lines"), list)
        and bool(payload["lines"])
        and not isinstance(payload.get("orders"), list)
        and bool(payload.get("customerOrderNumber"))
    )


def flatten(obj, prefix=""):
    paths = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            path = f"{prefix}.{key}" if prefix else key
            if key in ("additionalAttributes", "vmfAdditionalAttributes", "directShipConfigAttributes") and isinstance(value, list):
                paths.add(path)
                for item in value:
                    if isinstance(item, dict):
                        name = str(item.get("attributeName") or item.get("attributename") or "").strip()
                        if name:
                            paths.add(f"{path}[{name}]")
                continue
            if isinstance(value, (dict, list)):
                child = flatten(value, path)
                paths |= child
            else:
                if value is None or (isinstance(value, str) and not value.strip()):
                    continue
                paths.add(path)
    elif isinstance(obj, list):
        paths.add(prefix)
        for item in obj[:8]:
            paths |= flatten(item, f"{prefix}[]")
    return paths


def search(client, settings, text, frm, to, limit=100):
    query = build_checkout_query(search_text=text, service=services(), host=hosts())
    params = LogSearchParams(
        filter=LogSearchFilter(query=query, from_time=frm, to_time=to, storage_tier=settings.default_storage_tier),
        sort=settings.default_sort,
        page_limit=limit,
    )
    return query, search_logs(client, params)


def find_inbound(client, settings, po, frm, to):
    _q, events = search(client, settings, po, frm, to, limit=50)
    for event in events:
        req = extract_hermes_request(event)
        if not is_inbound(req):
            continue
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
            "success_verified": True,
        }
    return None


def collect(client, settings, order_type, frm, to, existing_pos):
    # No SUCCESS token — use ingramOrderNumber + zero line errors as success.
    text = f'resellerInfo "orderType":"{order_type}"'
    query, events = search(client, settings, text, frm, to, limit=100)
    print(f"\n=== {order_type} query: {query}")
    seen = {p.upper() for p in existing_pos}
    candidates = []
    scanned = 0
    for event in events:
        scanned += 1
        if scanned > MAX_SCAN:
            break
        payload = extract_hermes_request(event) or extract_hermes_response(event)
        if not is_success_echo(payload):
            continue
        if order_type.upper() not in order_types(payload):
            continue
        po = str(payload.get("customerOrderNumber") or "").strip()
        if not po or po.upper() in seen:
            continue
        # Prefer responses where ALL orders match the requested type (pure D / pure S)
        ots = order_types(payload)
        if not ots or any(t != order_type.upper() for t in ots):
            # Still accept if at least one matches and we need samples
            pass
        if order_type.upper() not in ots:
            continue
        seen.add(po.upper())
        candidates.append(po)
        if len(candidates) >= TARGET * 4:
            break
    print(f"  scanned={scanned} new_candidates={len(candidates)}")
    samples = []
    for po in candidates:
        if len(samples) >= TARGET:
            break
        print(f"  inbound {po}…", flush=True)
        inbound = find_inbound(client, settings, po, frm, to)
        if not inbound:
            print("    MISSING")
            continue
        inbound["response_order_type"] = order_type.upper()
        samples.append(inbound)
        print(f"    OK keys={list(inbound['request'].keys())[:10]}")
    return samples


def compare(d_samples, s_samples):
    d_stats = Counter()
    s_stats = Counter()
    for s in d_samples:
        d_stats.update(flatten(s["request"]))
    for s in s_samples:
        s_stats.update(flatten(s["request"]))
    n_d = max(len(d_samples), 1)
    n_s = max(len(s_samples), 1)
    rows = []
    for path in sorted(set(d_stats) | set(s_stats)):
        d_count = d_stats[path]
        s_count = s_stats[path]
        d_rate = d_count / n_d
        s_rate = s_count / n_s
        rows.append({
            "path": path,
            "d_count": d_count,
            "d_rate": round(d_rate, 2),
            "s_count": s_count,
            "s_rate": round(s_rate, 2),
            "delta_d_minus_s": round(d_rate - s_rate, 2),
        })
    return {
        "sample_counts": {"D": len(d_samples), "S": len(s_samples)},
        "d_characteristic_fields": sorted(
            [r for r in rows if r["d_rate"] >= 0.7 and r["s_rate"] <= 0.3],
            key=lambda r: (-r["delta_d_minus_s"], r["path"]),
        ),
        "present_in_all_d": [r for r in rows if r["d_rate"] == 1.0],
        "present_in_all_d_not_all_s": sorted(
            [r for r in rows if r["d_rate"] == 1.0 and r["s_rate"] < 1.0],
            key=lambda r: (r["s_rate"], r["path"]),
        ),
        "shared_always_present": [r for r in rows if r["d_rate"] == 1.0 and r["s_rate"] == 1.0],
        "all_field_presence": rows,
        "candidate_mandatory_for_d": [r["path"] for r in rows if r["d_rate"] == 1.0],
        "likely_d_specific_vs_s": [
            r["path"] for r in rows if r["d_rate"] >= 0.7 and r["s_rate"] <= 0.3
        ],
    }


def inspect_direct_ship(samples, label):
    print(f"\n--- directShipConfigAttributes in {label} ---")
    name_counter = Counter()
    samples_with = 0
    examples = []
    for s in samples:
        req = s["request"]
        found = False
        for line in req.get("lines") or []:
            if not isinstance(line, dict):
                continue
            dsc = line.get("directShipConfigAttributes")
            if isinstance(dsc, list) and dsc:
                found = True
                for item in dsc:
                    if isinstance(item, dict):
                        name_counter[str(item.get("attributeName") or "")] += 1
                if len(examples) < 2:
                    examples.append({
                        "po": s["customer_order_number"],
                        "lineType": line.get("lineType"),
                        "ingramPartNumber": line.get("ingramPartNumber"),
                        "vendorPartNumber": line.get("vendorPartNumber"),
                        "directShipConfigAttributes": dsc,
                        "line_additionalAttributes": line.get("additionalAttributes"),
                    })
        if found:
            samples_with += 1
    print(f"  samples_with_block={samples_with}/{len(samples)}")
    print(f"  attributeName counts: {dict(name_counter.most_common(30))}")
    return {
        "samples_with_block": samples_with,
        "attribute_name_counts": dict(name_counter.most_common()),
        "examples": examples,
    }


def line_summary(samples):
    lt = Counter()
    flags = Counter()
    for s in samples:
        for line in s["request"].get("lines") or []:
            if not isinstance(line, dict):
                continue
            lt[str(line.get("lineType") or "(blank)")] += 1
            for item in line.get("additionalAttributes") or []:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("attributeName") or "").lower()
                val = str(item.get("attributeValue") or "").lower()
                if "direct" in name or name in ("isdirectship", "costoverrideflag"):
                    flags[f"{name}={val}"] += 1
            if line.get("directShipConfigAttributes"):
                flags["has_directShipConfigAttributes"] += 1
    return {"lineType_counts": dict(lt), "flags": dict(flags)}


def main():
    settings = get_settings()
    frm, to = window(30)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load previous samples if present
    d_path = OUT_DIR / "d-samples.json"
    s_path = OUT_DIR / "s-samples.json"
    d_samples = json.loads(d_path.read_text(encoding="utf-8")) if d_path.exists() else []
    s_samples = json.loads(s_path.read_text(encoding="utf-8")) if s_path.exists() else []

    with DatadogClient(settings) as client:
        if len(d_samples) < TARGET:
            more = collect(
                client,
                settings,
                "D",
                frm,
                to,
                [s["customer_order_number"] for s in d_samples],
            )
            # keep unique
            have = {s["customer_order_number"].upper() for s in d_samples}
            for m in more:
                if m["customer_order_number"].upper() not in have:
                    d_samples.append(m)
                    have.add(m["customer_order_number"].upper())
                if len(d_samples) >= TARGET:
                    break
        if len(s_samples) < TARGET:
            more = collect(
                client,
                settings,
                "S",
                frm,
                to,
                [s["customer_order_number"] for s in s_samples],
            )
            have = {s["customer_order_number"].upper() for s in s_samples}
            for m in more:
                if m["customer_order_number"].upper() not in have:
                    s_samples.append(m)
                    have.add(m["customer_order_number"].upper())
                if len(s_samples) >= TARGET:
                    break

    d_samples = d_samples[:TARGET]
    s_samples = s_samples[:TARGET]
    d_path.write_text(json.dumps(d_samples, indent=2, default=str, ensure_ascii=False) + "\n", encoding="utf-8")
    s_path.write_text(json.dumps(s_samples, indent=2, default=str, ensure_ascii=False) + "\n", encoding="utf-8")

    comparison = compare(d_samples, s_samples)
    comparison["window"] = {"from": frm, "to": to}
    comparison["d_orders"] = [s["customer_order_number"] for s in d_samples]
    comparison["s_orders"] = [s["customer_order_number"] for s in s_samples]
    comparison["d_line_summary"] = line_summary(d_samples)
    comparison["s_line_summary"] = line_summary(s_samples)
    comparison["d_direct_ship_inspect"] = inspect_direct_ship(d_samples, "D")
    comparison["s_direct_ship_inspect"] = inspect_direct_ship(s_samples, "S")

    (OUT_DIR / "comparison.json").write_text(
        json.dumps(comparison, indent=2, default=str, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # Human-readable report
    report = []
    report.append("# D vs S Order Create v6 — Production SUCCESS comparison\n")
    report.append(f"Window: {frm} .. {to}\n")
    report.append(f"D samples ({len(d_samples)}): {comparison['d_orders']}\n")
    report.append(f"S samples ({len(s_samples)}): {comparison['s_orders']}\n")
    report.append("\n## Key finding\n")
    report.append(
        "`orderType` D/S is assigned on the **response** (`orders[].orderType`). "
        "The inbound v6 request does not send top-level `orderType`. "
        "D (direct-ship) orders are distinguished by request fields below.\n"
    )
    report.append("\n## Significant differences (high in D, low in S)\n")
    for r in comparison["d_characteristic_fields"][:40]:
        report.append(
            f"- `{r['path']}` — D={r['d_rate']:.0%} S={r['s_rate']:.0%}\n"
        )
    report.append("\n## Present in ALL D samples (candidate mandatory for D)\n")
    for path in comparison["candidate_mandatory_for_d"]:
        report.append(f"- `{path}`\n")
    report.append("\n## Present in ALL D but NOT all S\n")
    for r in comparison["present_in_all_d_not_all_s"]:
        report.append(f"- `{r['path']}` — S={r['s_rate']:.0%}\n")
    report.append("\n## Line summaries\n")
    report.append(f"- D: {comparison['d_line_summary']}\n")
    report.append(f"- S: {comparison['s_line_summary']}\n")
    report.append("\n## directShipConfigAttributes\n")
    report.append(f"- D: {comparison['d_direct_ship_inspect']['samples_with_block']}/{len(d_samples)} samples; "
                  f"attrs={comparison['d_direct_ship_inspect']['attribute_name_counts']}\n")
    report.append(f"- S: {comparison['s_direct_ship_inspect']['samples_with_block']}/{len(s_samples)} samples; "
                  f"attrs={comparison['s_direct_ship_inspect']['attribute_name_counts']}\n")

    (OUT_DIR / "REPORT.md").write_text("".join(report), encoding="utf-8")
    print("\n========== FINAL ==========")
    print(f"D={len(d_samples)} {comparison['d_orders']}")
    print(f"S={len(s_samples)} {comparison['s_orders']}")
    print("D-characteristic:")
    for r in comparison["d_characteristic_fields"][:30]:
        print(f"  {r['path']}: D={r['d_rate']} S={r['s_rate']}")
    print(f"Wrote {OUT_DIR/'REPORT.md'}")


if __name__ == "__main__":
    main()
