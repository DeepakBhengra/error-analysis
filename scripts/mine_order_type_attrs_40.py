"""Mine ~40 D and ~40 S SUCCESS inbound v6 requests; compare attributes.

Usage:
  .venv\\Scripts\\python scripts/mine_order_type_attrs_40.py
"""

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
TARGET = 40
MAX_SCAN = 2500
WINDOW_DAYS = 45
# Pure typed responses only (all orders[].orderType match).
REQUIRE_PURE = True


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


def _is_success_echo(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    orders = payload.get("orders")
    if not isinstance(orders, list) or not orders:
        return False
    for order in orders:
        if not isinstance(order, dict):
            continue
        if order.get("ingramOrderNumber"):
            errs = order.get("numberOfLinesWithError")
            if errs in (0, "0", None):
                return True
    return False


def _is_inbound(payload: Any) -> bool:
    return (
        isinstance(payload, dict)
        and isinstance(payload.get("lines"), list)
        and bool(payload["lines"])
        and not isinstance(payload.get("orders"), list)
        and bool(str(payload.get("customerOrderNumber") or "").strip())
    )


def _search(client: DatadogClient, settings: Any, text: str, frm: str, to: str, limit: int = 100):
    query = build_checkout_query(
        search_text=text,
        service=_services(),
        host=_hosts(),
    )
    params = LogSearchParams(
        filter=LogSearchFilter(
            query=query,
            from_time=frm,
            to_time=to,
            storage_tier=settings.default_storage_tier,
        ),
        sort=settings.default_sort,
        page_limit=limit,
    )
    return query, search_logs(client, params)


def _find_inbound(client: DatadogClient, settings: Any, po: str, frm: str, to: str) -> dict[str, Any] | None:
    _q, events = _search(client, settings, po, frm, to, limit=50)
    for event in events:
        req = extract_hermes_request(event)
        if not _is_inbound(req):
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
            "success_verified": True,
        }
    return None


def _collect_candidates(
    client: DatadogClient,
    settings: Any,
    order_type: str,
    frm: str,
    to: str,
    *,
    exclude: set[str],
    want: int,
) -> list[str]:
    text = f'resellerInfo "orderType":"{order_type}"'
    query, events = _search(client, settings, text, frm, to, limit=100)
    print(f"\n=== Candidates {order_type}: {query}")
    seen = set(exclude)
    candidates: list[str] = []
    scanned = 0
    for event in events:
        scanned += 1
        if scanned > MAX_SCAN:
            break
        payload = extract_hermes_request(event) or extract_hermes_response(event)
        if not _is_success_echo(payload):
            continue
        ots = _order_types(payload)
        if order_type.upper() not in ots:
            continue
        if REQUIRE_PURE and any(t != order_type.upper() for t in ots):
            continue
        po = str(payload.get("customerOrderNumber") or "").strip()
        if not po or po.upper() in seen:
            continue
        seen.add(po.upper())
        candidates.append(po)
        if len(candidates) >= want * 3:
            break
    print(f"  scanned={scanned} candidates={len(candidates)}")
    return candidates


def _load_existing(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


def _attr_names(attrs: Any) -> set[str]:
    names: set[str] = set()
    if not isinstance(attrs, list):
        return names
    for item in attrs:
        if isinstance(item, dict):
            name = str(item.get("attributeName") or item.get("attributename") or "").strip()
            if name:
                names.add(name)
    return names


def _top_level_keys(req: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for key, value in req.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, (list, dict)) and not value:
            # empty containers still count as present structurally
            keys.add(key)
            continue
        keys.add(key)
    return keys


def _line_keys(req: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for line in req.get("lines") or []:
        if not isinstance(line, dict):
            continue
        for key, value in line.items():
            if value is None:
                continue
            if isinstance(value, str) and not value.strip():
                continue
            keys.add(f"lines[].{key}")
    return keys


def _sample_attr_sets(sample: dict[str, Any]) -> dict[str, set[str]]:
    req = sample["request"]
    header_attrs = _attr_names(req.get("additionalAttributes"))
    vmf_attrs = _attr_names(req.get("vmfAdditionalAttributes"))
    line_attrs: set[str] = set()
    dsc_attrs: set[str] = set()
    line_vmf_attrs: set[str] = set()
    for line in req.get("lines") or []:
        if not isinstance(line, dict):
            continue
        line_attrs |= _attr_names(line.get("additionalAttributes"))
        dsc_attrs |= _attr_names(line.get("directShipConfigAttributes"))
        line_vmf_attrs |= _attr_names(line.get("vmfAdditionalAttributes"))
    return {
        "top_level": _top_level_keys(req),
        "header_additionalAttributes": header_attrs,
        "vmfAdditionalAttributes": vmf_attrs,
        "line_additionalAttributes": line_attrs,
        "directShipConfigAttributes": dsc_attrs,
        "line_vmfAdditionalAttributes": line_vmf_attrs,
        "line_fields": _line_keys(req),
    }


def _presence_rates(
    samples: list[dict[str, Any]],
) -> dict[str, dict[str, float]]:
    """category -> attr -> rate"""
    totals: dict[str, Counter[str]] = defaultdict(Counter)
    n = max(len(samples), 1)
    for sample in samples:
        sets = _sample_attr_sets(sample)
        for category, names in sets.items():
            for name in names:
                totals[category][name] += 1
    return {
        category: {name: count / n for name, count in counter.items()}
        for category, counter in totals.items()
    }


def _compare_category(
    d_rates: dict[str, float],
    s_rates: dict[str, float],
    *,
    specific_min: float = 0.25,
    specific_other_max: float = 0.10,
    common_min: float = 0.70,
) -> dict[str, Any]:
    all_names = sorted(set(d_rates) | set(s_rates))
    rows = []
    for name in all_names:
        d = d_rates.get(name, 0.0)
        s = s_rates.get(name, 0.0)
        rows.append(
            {
                "name": name,
                "d_rate": round(d, 3),
                "s_rate": round(s, 3),
                "delta": round(d - s, 3),
            }
        )
    d_specific = [
        r for r in rows if r["d_rate"] >= specific_min and r["s_rate"] <= specific_other_max
    ]
    s_specific = [
        r for r in rows if r["s_rate"] >= specific_min and r["d_rate"] <= specific_other_max
    ]
    common = [
        r for r in rows if r["d_rate"] >= common_min and r["s_rate"] >= common_min
    ]
    d_enriched = [
        r for r in rows if r["delta"] >= 0.25 and r["d_rate"] >= 0.30 and r["s_rate"] > specific_other_max
    ]
    s_enriched = [
        r
        for r in rows
        if (-r["delta"]) >= 0.25 and r["s_rate"] >= 0.30 and r["d_rate"] > specific_other_max
    ]
    d_specific.sort(key=lambda r: (-r["delta"], -r["d_rate"], r["name"]))
    s_specific.sort(key=lambda r: (r["delta"], -r["s_rate"], r["name"]))
    common.sort(key=lambda r: (-min(r["d_rate"], r["s_rate"]), r["name"]))
    d_enriched.sort(key=lambda r: (-r["delta"], r["name"]))
    s_enriched.sort(key=lambda r: (r["delta"], r["name"]))
    return {
        "d_specific": d_specific,
        "s_specific": s_specific,
        "common": common,
        "d_enriched_not_exclusive": d_enriched,
        "s_enriched_not_exclusive": s_enriched,
        "all": sorted(rows, key=lambda r: (-abs(r["delta"]), r["name"])),
    }


def _write_report(
    *,
    frm: str,
    to: str,
    d_samples: list[dict[str, Any]],
    s_samples: list[dict[str, Any]],
    comparison: dict[str, Any],
) -> str:
    lines: list[str] = []
    lines.append("# D vs S V6 request attributes (expanded sample)\n\n")
    lines.append(f"- Window: `{frm}` .. `{to}`\n")
    lines.append(f"- D samples: **{len(d_samples)}** pure SUCCESS response orderType=D\n")
    lines.append(f"- S samples: **{len(s_samples)}** pure SUCCESS response orderType=S\n")
    lines.append(
        "- Source: prod hosts `uschileai1401–1404` "
        "(`AsyncOrderCreate` / `OrderCreate_v6*`)\n\n"
    )
    lines.append("## Sample POs\n\n")
    lines.append(
        "**D:** "
        + ", ".join(s["customer_order_number"] for s in d_samples)
        + "\n\n"
    )
    lines.append(
        "**S:** "
        + ", ".join(s["customer_order_number"] for s in s_samples)
        + "\n\n"
    )

    lines.append("## D-type specific attributes\n\n")
    lines.append(
        "Present on ≥25% of D and ≤10% of S (exclusive / near-exclusive to D).\n\n"
    )
    for category, block in comparison.items():
        d_spec = block["d_specific"]
        if not d_spec:
            continue
        lines.append(f"### `{category}`\n\n")
        lines.append("| Attribute | D rate | S rate | delta |\n|---|---:|---:|---:|\n")
        for row in d_spec:
            lines.append(
                f"| `{row['name']}` | {row['d_rate']:.0%} | {row['s_rate']:.0%} | "
                f"{row['delta']:+.0%} |\n"
            )
        lines.append("\n")

    lines.append("## S-type specific attributes\n\n")
    lines.append(
        "Present on ≥25% of S and ≤10% of D (exclusive / near-exclusive to S).\n\n"
    )
    for category, block in comparison.items():
        s_spec = block["s_specific"]
        if not s_spec:
            continue
        lines.append(f"### `{category}`\n\n")
        lines.append("| Attribute | D rate | S rate | delta |\n|---|---:|---:|---:|\n")
        for row in s_spec:
            lines.append(
                f"| `{row['name']}` | {row['d_rate']:.0%} | {row['s_rate']:.0%} | "
                f"{row['delta']:+.0%} |\n"
            )
        lines.append("\n")

    lines.append("## Enriched on D (not exclusive)\n\n")
    lines.append("Higher on D by ≥25 points, but also appears on some S.\n\n")
    for category, block in comparison.items():
        rows = block["d_enriched_not_exclusive"]
        if not rows:
            continue
        lines.append(f"### `{category}`\n\n")
        lines.append("| Attribute | D rate | S rate | delta |\n|---|---:|---:|---:|\n")
        for row in rows[:40]:
            lines.append(
                f"| `{row['name']}` | {row['d_rate']:.0%} | {row['s_rate']:.0%} | "
                f"{row['delta']:+.0%} |\n"
            )
        lines.append("\n")

    lines.append("## Enriched on S (not exclusive)\n\n")
    for category, block in comparison.items():
        rows = block["s_enriched_not_exclusive"]
        if not rows:
            continue
        lines.append(f"### `{category}`\n\n")
        lines.append("| Attribute | D rate | S rate | delta |\n|---|---:|---:|---:|\n")
        for row in rows[:40]:
            lines.append(
                f"| `{row['name']}` | {row['d_rate']:.0%} | {row['s_rate']:.0%} | "
                f"{row['delta']:+.0%} |\n"
            )
        lines.append("\n")

    lines.append("## Common attributes (≥70% on both)\n\n")
    for category, block in comparison.items():
        rows = block["common"]
        if not rows:
            continue
        lines.append(f"### `{category}`\n\n")
        lines.append("| Attribute | D rate | S rate |\n|---|---:|---:|\n")
        for row in rows:
            lines.append(
                f"| `{row['name']}` | {row['d_rate']:.0%} | {row['s_rate']:.0%} |\n"
            )
        lines.append("\n")

    lines.append("## Notes\n\n")
    lines.append(
        "- Response `orders[].orderType` is D/S; inbound requests rarely set a meaningful "
        "`additionalAttributes.orderType`.\n"
    )
    lines.append(
        "- D-specific markers concentrate in `directShipConfigAttributes` and related "
        "direct-ship / VMF cost fields.\n"
    )
    lines.append(
        "- S-specific markers (if any) tend to be stock/warehouse / portal path fields "
        "rather than direct-ship config.\n"
    )
    return "".join(lines)


def main() -> int:
    settings = get_settings()
    frm, to = _window()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    d_path = OUT_DIR / "d-samples-40.json"
    s_path = OUT_DIR / "s-samples-40.json"

    # Seed from prior 10-sample files when present.
    prior_d = _load_existing(OUT_DIR / "d-samples.json")
    prior_s = _load_existing(OUT_DIR / "s-samples.json")
    d_samples = _load_existing(d_path) or list(prior_d)
    s_samples = _load_existing(s_path) or list(prior_s)

    # De-dupe by PO
    def uniq(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for sample in samples:
            po = str(sample.get("customer_order_number") or "").upper()
            if not po or po in seen:
                continue
            seen.add(po)
            out.append(sample)
        return out

    d_samples = uniq(d_samples)
    s_samples = uniq(s_samples)

    with DatadogClient(settings) as client:
        if len(d_samples) < TARGET:
            exclude = {s["customer_order_number"].upper() for s in d_samples}
            exclude |= {s["customer_order_number"].upper() for s in s_samples}
            candidates = _collect_candidates(
                client,
                settings,
                "D",
                frm,
                to,
                exclude=exclude,
                want=TARGET - len(d_samples),
            )
            for po in candidates:
                if len(d_samples) >= TARGET:
                    break
                print(f"  D inbound {po}…", flush=True)
                inbound = _find_inbound(client, settings, po, frm, to)
                if not inbound:
                    print("    MISSING")
                    continue
                inbound["response_order_type"] = "D"
                d_samples.append(inbound)
                print(f"    OK ({len(d_samples)}/{TARGET})")
                # checkpoint
                if len(d_samples) % 5 == 0:
                    d_path.write_text(
                        json.dumps(d_samples, indent=2, default=str, ensure_ascii=False)
                        + "\n",
                        encoding="utf-8",
                    )

        if len(s_samples) < TARGET:
            exclude = {s["customer_order_number"].upper() for s in d_samples}
            exclude |= {s["customer_order_number"].upper() for s in s_samples}
            candidates = _collect_candidates(
                client,
                settings,
                "S",
                frm,
                to,
                exclude=exclude,
                want=TARGET - len(s_samples),
            )
            for po in candidates:
                if len(s_samples) >= TARGET:
                    break
                print(f"  S inbound {po}…", flush=True)
                inbound = _find_inbound(client, settings, po, frm, to)
                if not inbound:
                    print("    MISSING")
                    continue
                inbound["response_order_type"] = "S"
                s_samples.append(inbound)
                print(f"    OK ({len(s_samples)}/{TARGET})")
                if len(s_samples) % 5 == 0:
                    s_path.write_text(
                        json.dumps(s_samples, indent=2, default=str, ensure_ascii=False)
                        + "\n",
                        encoding="utf-8",
                    )

    d_samples = uniq(d_samples)[:TARGET]
    s_samples = uniq(s_samples)[:TARGET]

    # Drop any accidental overlap
    overlap = {
        s["customer_order_number"].upper() for s in d_samples
    } & {s["customer_order_number"].upper() for s in s_samples}
    if overlap:
        print(f"Dropping overlap POs: {sorted(overlap)}")
        d_samples = [
            s for s in d_samples if s["customer_order_number"].upper() not in overlap
        ]
        s_samples = [
            s for s in s_samples if s["customer_order_number"].upper() not in overlap
        ]

    d_path.write_text(
        json.dumps(d_samples, indent=2, default=str, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    s_path.write_text(
        json.dumps(s_samples, indent=2, default=str, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    d_rates = _presence_rates(d_samples)
    s_rates = _presence_rates(s_samples)
    categories = sorted(set(d_rates) | set(s_rates))
    comparison = {
        category: _compare_category(
            d_rates.get(category, {}),
            s_rates.get(category, {}),
        )
        for category in categories
    }

    payload = {
        "window": {"from": frm, "to": to},
        "sample_counts": {"D": len(d_samples), "S": len(s_samples)},
        "d_orders": [s["customer_order_number"] for s in d_samples],
        "s_orders": [s["customer_order_number"] for s in s_samples],
        "comparison": comparison,
    }
    (OUT_DIR / "attribute-comparison-40.json").write_text(
        json.dumps(payload, indent=2, default=str, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    report = _write_report(
        frm=frm,
        to=to,
        d_samples=d_samples,
        s_samples=s_samples,
        comparison=comparison,
    )
    (OUT_DIR / "ATTRIBUTE-REPORT-40.md").write_text(report, encoding="utf-8")

    print("\n========== DONE ==========")
    print(f"D={len(d_samples)} S={len(s_samples)}")
    print("D-specific counts by category:")
    for category, block in comparison.items():
        print(f"  {category}: {len(block['d_specific'])} D-specific, {len(block['s_specific'])} S-specific")
    print(f"Wrote {OUT_DIR / 'ATTRIBUTE-REPORT-40.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
