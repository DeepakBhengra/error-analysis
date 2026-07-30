"""Mine Order Create v2/v6 request pairs from Datadog and diff them.

Workflow:
1. Search OrderCreate_v6 / uschileai2503 for RequestLogPayload + JobID.
2. For each JobID, find the sibling OrderCreate_v2 / uschileai2501 request.
3. Persist pairs, convert v2 -> v6, and report rule gaps vs actual v6.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from error_analysis.config import Settings
from error_analysis.datadog.client import DatadogClient
from error_analysis.datadog.models import LogSearchFilter, LogSearchParams
from error_analysis.datadog.query_builder import build_checkout_query
from error_analysis.datadog.search import search_logs
from error_analysis.extractors.hermes_request import extract_hermes_request
from error_analysis.extractors.request_log_payload import (
    extract_correlation_id,
    extract_job_id,
)
from error_analysis.order_create.v2_to_v6 import (
    OrderCreateV2ToV6Error,
    convert_v2_to_v6,
)

V6_SERVICE = "OrderCreate_v6"
V6_HOST = "uschileai2503"
# Portal reseller body lives in "V6 starter request" logs (contains resellerInfo).
# Free-text OrderCreate_v6_0 matches many non-portal sidecar logs without lines[].
V6_PORTAL_SEARCH_TEXT = "resellerInfo"

V2_SERVICE = "OrderCreate_v2"
V2_HOST = "uschileai2501"
V2_HOST_FALLBACKS: tuple[str | None, ...] = (
    "uschileai2501",
    "uschleai3501",
    None,  # any host
)
V2_SERVICE_NAME_TEXT = "OrderCreate_v2_0"

# Paths (relative to the v6 root) that are master-data enrichment and cannot
# be reconstructed from the v2 request alone.
ENRICHMENT_PATH_PREFIXES: tuple[str, ...] = (
    "notes",
    "resellerInfo.companyName",
    "resellerInfo.contact",
    "resellerInfo.addressLine1",
    "resellerInfo.addressLine2",
    "resellerInfo.addressLine3",
    "resellerInfo.city",
    "resellerInfo.state",
    "resellerInfo.postalCode",
    "resellerInfo.countryCode",
    "resellerInfo.phoneNumber",
    "shipToInfo.companyName",
    "shipToInfo.name1",
    "shipToInfo.name2",
    "shipToInfo.addressLine1",
    "shipToInfo.addressLine2",
    "shipToInfo.addressLine3",
    "shipToInfo.addressLine4",
    "shipToInfo.city",
    "shipToInfo.state",
    "shipToInfo.postalCode",
    "shipToInfo.countryCode",
    "shipToInfo.phoneNumber",
    "shipToInfo.email",
    "endUserInfo.addressSequenceNumber",
    "endUserInfo.segmentation",
    "endUserInfo.contact",  # often master-data composed / trailing spaces
    "endUserInfo.name2",
    "endUserInfo.name3",
    "endUserInfo.addressLine2",
    "endUserInfo.addressLine3",
    "endUserInfo.addressLine4",
    "endUserInfo.city",
    "endUserInfo.state",
    "endUserInfo.postalCode",
    "endUserInfo.countryCode",
)

_ATTR_LIST_KEYS = frozenset(
    {
        "additionalAttributes",
        "vmfAdditionalAttributes",
        "vmfspecs",
        "productextendedspecs",
        "serviceextendedspecs",
    }
)


@dataclass
class PairDiff:
    path: str
    kind: str  # missing | extra | value_mismatch
    expected: Any = None
    actual: Any = None
    enrichment: bool = False


@dataclass
class PairCompareResult:
    job_id: str
    rule_gaps: list[PairDiff] = field(default_factory=list)
    enrichment_diffs: list[PairDiff] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and not self.rule_gaps


def default_training_window(days: int = 15) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    return (
        start.isoformat().replace("+00:00", "Z"),
        now.isoformat().replace("+00:00", "Z"),
    )


def default_validation_window(
    train_days: int = 15, validate_days: int = 10
) -> tuple[str, str]:
    """Window immediately before the training window (days train..train+validate)."""
    now = datetime.now(timezone.utc)
    end = now - timedelta(days=train_days)
    start = end - timedelta(days=validate_days)
    return (
        start.isoformat().replace("+00:00", "Z"),
        end.isoformat().replace("+00:00", "Z"),
    )


def _safe_filename(job_id: str) -> str:
    cleaned = re.sub(r"[^\w.\-]+", "_", job_id.strip())
    return cleaned or "unknown-job"


def _is_portal_v6_body(payload: Any) -> bool:
    """True for reseller portal Order Create v6 request bodies."""
    return (
        isinstance(payload, dict)
        and isinstance(payload.get("customerOrderNumber"), str)
        and payload["customerOrderNumber"].strip()
        and isinstance(payload.get("lines"), list)
        and ("resellerInfo" in payload or "additionalAttributes" in payload)
    )


def _is_v2_body(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if "ordercreaterequest" in payload:
        return True
    return "customerponumber" in payload or "ordercreatedetails" in payload


def _customer_key_from_v6(payload: dict[str, Any]) -> str:
    return str(payload.get("customerOrderNumber") or "").strip().upper()


def _customer_key_from_v2(payload: dict[str, Any]) -> str:
    node = payload
    if isinstance(node.get("ordercreaterequest"), dict):
        node = node["ordercreaterequest"]
    if isinstance(node.get("ordercreatedetails"), dict):
        node = node["ordercreatedetails"]
    return str(node.get("customerponumber") or "").strip().upper()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, default=str, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _search_events(
    client: DatadogClient,
    settings: Settings,
    *,
    query: str,
    from_time: str,
    to_time: str,
    page_limit: int | None = None,
) -> list[dict[str, Any]]:
    params = LogSearchParams(
        filter=LogSearchFilter(
            query=query,
            **{"from": from_time, "to": to_time},
            storage_tier=settings.default_storage_tier,
        ),
        sort=settings.default_sort,
        page_limit=page_limit or settings.default_page_limit,
    )
    return list(search_logs(client, params))


def _correlation_from_v6_body(payload: dict[str, Any]) -> str | None:
    """Fall back to IM-CORRELATIONID inside v6 additionalAttributes."""
    attrs = payload.get("additionalAttributes")
    if not isinstance(attrs, list):
        return None
    for item in attrs:
        if not isinstance(item, dict):
            continue
        name = item.get("attributeName") or item.get("attributename")
        if isinstance(name, str) and name.upper() == "IM-CORRELATIONID":
            value = item.get("attributeValue") or item.get("attributevalue")
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def find_v2_request(
    client: DatadogClient,
    settings: Settings,
    *,
    correlation_id: str | None,
    job_id: str | None,
    customer_order_number: str | None,
    from_time: str,
    to_time: str,
) -> dict[str, Any] | None:
    """Locate the OrderCreate_v2 RequestLogPayload for a linked v6 request.

    Empirically JobIDs differ between OrderCreate_v2 and OrderCreate_v6, and
    CorrelationIDs are reused across many orders. The reliable join key is
    ``customerOrderNumber`` / ``customerponumber``. CorrelationID / JobID are
    kept as secondary lookups.
    """
    target_po = (customer_order_number or "").strip().upper() or None
    queries: list[str] = []
    if target_po:
        for host in V2_HOST_FALLBACKS:
            queries.append(
                build_checkout_query(
                    search_text=target_po,
                    service=V2_SERVICE,
                    host=host,
                )
            )
    if job_id:
        for host in V2_HOST_FALLBACKS:
            queries.append(
                build_checkout_query(
                    job_id=job_id,
                    search_text=V2_SERVICE_NAME_TEXT,
                    service=V2_SERVICE,
                    host=host,
                )
            )
    if correlation_id and target_po:
        queries.append(
            build_checkout_query(
                correlation_id=correlation_id,
                search_text=target_po,
                service=V2_SERVICE,
                host=None,
            )
        )

    for query in queries:
        for event in _search_events(
            client,
            settings,
            query=query,
            from_time=from_time,
            to_time=to_time,
            page_limit=50,
        ):
            payload = extract_hermes_request(event)
            if not _is_v2_body(payload):
                continue
            assert isinstance(payload, dict)
            if target_po and _customer_key_from_v2(payload) != target_po:
                continue
            return payload
    return None


# Backward-compatible alias used by older imports/tests.
def find_v2_request_for_job(
    client: DatadogClient,
    settings: Settings,
    *,
    job_id: str,
    from_time: str,
    to_time: str,
) -> dict[str, Any] | None:
    return find_v2_request(
        client,
        settings,
        correlation_id=None,
        job_id=job_id,
        customer_order_number=None,
        from_time=from_time,
        to_time=to_time,
    )


def mine_pairs(
    settings: Settings,
    *,
    from_time: str,
    to_time: str,
    count: int = 20,
    out_dir: Path | None = None,
    page_limit: int | None = None,
    max_v6_events: int = 500,
    search_text: str | None = None,
    host: str | None = V6_HOST,
    exclude_customers: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Mine up to ``count`` distinct v2/v6 request pairs linked by customer PO."""
    if count < 1:
        raise ValueError("count must be >= 1")

    destination = out_dir or Path("results/v2v6-pairs")
    destination.mkdir(parents=True, exist_ok=True)

    query = build_checkout_query(
        search_text=search_text or V6_PORTAL_SEARCH_TEXT,
        service=V6_SERVICE,
        host=host,
    )
    excluded = {item.strip().upper() for item in (exclude_customers or set()) if item}

    pairs: list[dict[str, Any]] = []
    seen_customers: set[str] = set(excluded)
    scanned = 0
    skipped_no_v2 = 0
    skipped_no_po = 0
    skipped_excluded = 0

    with DatadogClient(settings) as client:
        for event in _search_events(
            client,
            settings,
            query=query,
            from_time=from_time,
            to_time=to_time,
            page_limit=page_limit or 100,
        ):
            scanned += 1
            if scanned > max_v6_events:
                break

            v6_request = extract_hermes_request(event)
            if not _is_portal_v6_body(v6_request):
                continue
            assert isinstance(v6_request, dict)

            customer = _customer_key_from_v6(v6_request)
            if not customer:
                skipped_no_po += 1
                continue
            if customer in excluded:
                skipped_excluded += 1
                continue
            if customer in seen_customers:
                continue

            job_id = extract_job_id(event)
            correlation_id = extract_correlation_id(event) or _correlation_from_v6_body(
                v6_request
            )

            v2_request = find_v2_request(
                client,
                settings,
                correlation_id=correlation_id,
                job_id=job_id,
                customer_order_number=customer,
                from_time=from_time,
                to_time=to_time,
            )
            if v2_request is None:
                skipped_no_v2 += 1
                seen_customers.add(customer)
                continue

            attributes = event.get("attributes") or {}
            pair = {
                "job_id": job_id,
                "correlation_id": correlation_id,
                "customer_order_number": customer,
                "timestamp": attributes.get("timestamp"),
                "v6_log_id": event.get("id"),
                "v6_service": attributes.get("service"),
                "v6_host": attributes.get("host"),
                "v6_request": v6_request,
                "v2_request": v2_request,
            }
            path = destination / f"{_safe_filename(customer)}.json"
            _write_json(path, pair)
            pairs.append(pair)
            seen_customers.add(customer)
            if len(pairs) >= count:
                break

    _write_json(
        destination / "_mine_summary.json",
        {
            "requested": count,
            "found": len(pairs),
            "scanned_v6_events": scanned,
            "skipped_no_v2": skipped_no_v2,
            "skipped_no_po": skipped_no_po,
            "skipped_excluded": skipped_excluded,
            "query": query,
            "from_time": from_time,
            "to_time": to_time,
            "join_strategy": "customer_order_number_primary",
        },
    )
    return pairs


def load_pairs(pairs_dir: Path) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    if not pairs_dir.exists():
        return pairs
    for path in sorted(pairs_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and "v2_request" in data and "v6_request" in data:
            pairs.append(data)
    return pairs


def _is_enrichment_path(path: str) -> bool:
    for prefix in ENRICHMENT_PATH_PREFIXES:
        if path == prefix or path.startswith(prefix + ".") or path.startswith(
            prefix + "["
        ):
            return True
    if re.search(
        r"(^|\.)endUserInfo\[\d+\]\.(city|state|postalCode|countryCode|"
        r"segmentation|addressSequenceNumber|name2|name3|addressLine[2-4])$",
        path,
    ):
        return True
    # Warranty line blocks are not reconstructed from v2 today.
    if re.match(r"^lines\[\d+\]\.warrantyInfo(\.|$)", path):
        return True
    # Warehouse id is sometimes enriched onto v6 when absent from v2.
    if re.match(
        r"^lines\[\d+\]\.additionalAttributes\[shipFromWareHouseId\]$",
        path,
    ):
        return True
    return False


def _attr_list_as_multiset(items: Any) -> Counter[tuple[str, str]]:
    counter: Counter[tuple[str, str]] = Counter()
    if not isinstance(items, list):
        return counter
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("attributeName")
        if name is None:
            name = item.get("attributename")
        value = item.get("attributeValue")
        if value is None:
            value = item.get("attributevalue")
        if not isinstance(name, str):
            continue
        counter[(name, "" if value is None else str(value))] += 1
    return counter


def _diff_attr_lists(
    expected: Any,
    actual: Any,
    path: str,
    diffs: list[PairDiff],
) -> None:
    exp = _attr_list_as_multiset(expected)
    act = _attr_list_as_multiset(actual)
    for key, count in (exp - act).items():
        for _ in range(count):
            diffs.append(
                PairDiff(
                    path=f"{path}[{key[0]}]",
                    kind="missing",
                    expected=key[1],
                    actual=None,
                    enrichment=_is_enrichment_path(f"{path}[{key[0]}]"),
                )
            )
    for key, count in (act - exp).items():
        for _ in range(count):
            diffs.append(
                PairDiff(
                    path=f"{path}[{key[0]}]",
                    kind="extra",
                    expected=None,
                    actual=key[1],
                    enrichment=_is_enrichment_path(f"{path}[{key[0]}]"),
                )
            )


def _diff_values(
    expected: Any,
    actual: Any,
    path: str,
    diffs: list[PairDiff],
) -> None:
    if expected == actual:
        return

    key = path.rsplit(".", 1)[-1] if path else ""
    if key in _ATTR_LIST_KEYS or (
        isinstance(expected, list)
        and expected
        and isinstance(expected[0], dict)
        and ("attributeName" in expected[0] or "attributename" in expected[0])
    ):
        _diff_attr_lists(expected, actual, path or "$", diffs)
        return

    if isinstance(expected, dict) and isinstance(actual, dict):
        keys = set(expected) | set(actual)
        for child in sorted(keys):
            child_path = f"{path}.{child}" if path else child
            if child not in actual:
                diffs.append(
                    PairDiff(
                        path=child_path,
                        kind="missing",
                        expected=expected[child],
                        actual=None,
                        enrichment=_is_enrichment_path(child_path),
                    )
                )
            elif child not in expected:
                diffs.append(
                    PairDiff(
                        path=child_path,
                        kind="extra",
                        expected=None,
                        actual=actual[child],
                        enrichment=_is_enrichment_path(child_path),
                    )
                )
            else:
                _diff_values(expected[child], actual[child], child_path, diffs)
        return

    if isinstance(expected, list) and isinstance(actual, list):
        # Compare by index for structured lists (lines, vmf, endUserInfo).
        max_len = max(len(expected), len(actual))
        for index in range(max_len):
            child_path = f"{path}[{index}]"
            if index >= len(actual):
                diffs.append(
                    PairDiff(
                        path=child_path,
                        kind="missing",
                        expected=expected[index],
                        actual=None,
                        enrichment=_is_enrichment_path(child_path),
                    )
                )
            elif index >= len(expected):
                diffs.append(
                    PairDiff(
                        path=child_path,
                        kind="extra",
                        expected=None,
                        actual=actual[index],
                        enrichment=_is_enrichment_path(child_path),
                    )
                )
            else:
                _diff_values(expected[index], actual[index], child_path, diffs)
        return

    # Treat trailing/leading whitespace-only differences as enrichment noise.
    if (
        isinstance(expected, str)
        and isinstance(actual, str)
        and expected.strip() == actual.strip()
    ):
        diffs.append(
            PairDiff(
                path=path or "$",
                kind="value_mismatch",
                expected=expected,
                actual=actual,
                enrichment=True,
            )
        )
        return

    # customerOrderNumber / endCustomerOrderNumber case folding.
    if (
        (path or "") in {"customerOrderNumber", "endCustomerOrderNumber"}
        and isinstance(expected, str)
        and isinstance(actual, str)
        and expected.upper() == actual.upper()
    ):
        diffs.append(
            PairDiff(
                path=path or "$",
                kind="value_mismatch",
                expected=expected,
                actual=actual,
                enrichment=True,
            )
        )
        return

    diffs.append(
        PairDiff(
            path=path or "$",
            kind="value_mismatch",
            expected=expected,
            actual=actual,
            enrichment=_is_enrichment_path(path or "$"),
        )
    )


def compare_pair(
    v2_request: dict[str, Any],
    v6_actual: dict[str, Any],
    *,
    job_id: str = "",
) -> PairCompareResult:
    """Convert v2 and deep-diff against the actual v6 payload."""
    try:
        converted = convert_v2_to_v6(v2_request)
    except OrderCreateV2ToV6Error as exc:
        return PairCompareResult(job_id=job_id, error=str(exc))

    diffs: list[PairDiff] = []
    _diff_values(v6_actual, converted, "", diffs)

    rule_gaps = [diff for diff in diffs if not diff.enrichment]
    enrichment = [diff for diff in diffs if diff.enrichment]
    return PairCompareResult(
        job_id=job_id,
        rule_gaps=rule_gaps,
        enrichment_diffs=enrichment,
    )


def _serialize_diff(diff: PairDiff) -> dict[str, Any]:
    return {
        "path": diff.path,
        "kind": diff.kind,
        "expected": diff.expected,
        "actual": diff.actual,
        "enrichment": diff.enrichment,
    }


def run_report(
    pairs_dir: Path,
    *,
    out_path: Path | None = None,
) -> dict[str, Any]:
    """Compare all pairs in a directory and write an aggregated report."""
    pairs = load_pairs(pairs_dir)
    results: list[dict[str, Any]] = []
    gap_counter: Counter[str] = Counter()
    ok_count = 0

    for pair in pairs:
        job_id = str(pair.get("job_id") or "")
        v2 = pair.get("v2_request")
        v6 = pair.get("v6_request")
        if not isinstance(v2, dict) or not isinstance(v6, dict):
            results.append(
                {
                    "job_id": job_id,
                    "ok": False,
                    "error": "Pair is missing v2_request or v6_request object.",
                }
            )
            continue

        compared = compare_pair(v2, v6, job_id=job_id)
        if compared.ok:
            ok_count += 1
        for gap in compared.rule_gaps:
            gap_counter[f"{gap.kind}:{gap.path}"] += 1

        results.append(
            {
                "job_id": job_id,
                "ok": compared.ok,
                "error": compared.error,
                "rule_gap_count": len(compared.rule_gaps),
                "enrichment_diff_count": len(compared.enrichment_diffs),
                "rule_gaps": [_serialize_diff(d) for d in compared.rule_gaps],
                "enrichment_diffs": [
                    _serialize_diff(d) for d in compared.enrichment_diffs
                ],
            }
        )

    report = {
        "pairs_dir": str(pairs_dir),
        "pair_count": len(pairs),
        "ok_count": ok_count,
        "rule_gap_pairs": len(pairs) - ok_count,
        "aggregated_rule_gaps": [
            {"key": key, "count": count}
            for key, count in gap_counter.most_common()
        ],
        "pairs": results,
    }

    destination = out_path or (pairs_dir.parent / "v2v6-rule-report.json")
    _write_json(destination, report)
    report["report_path"] = str(destination)
    return report
