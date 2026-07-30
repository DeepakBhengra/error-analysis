from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from error_analysis.extractors.order_create_v2_response import (
    extract_v2_response_from_record,
    extract_xml_statuscode,
    parse_v2_response_text,
)
from error_analysis.error_lookup.client import is_two_char_error_code
Outcome = Literal["SUCCESS", "FAILED", "UNKNOWN"]


@dataclass(frozen=True)
class ResponseCheckResult:
    outcome: Outcome
    statuscode: str
    responsemessage: str
    errorcode: str
    responsestatus: str
    globalorderid: str
    raw_preamble: dict[str, Any]
    response_payload: dict[str, Any] | None
    source_log_id: str | None
    customer_order_number: str = ""
    source_service: str = ""


def is_v6_response_service(service: Any) -> bool:
    """True for OrderCreate_v6-family services (e.g. OrderCreate_v6_0).

    The v6 'OrderCreate Response formed' log carries the authoritative
    responsepreamble (statuscode/responsemessage) and must win over sibling
    v2 XML or note logs (e.g. WY address notes) for the same order.
    """
    return isinstance(service, str) and service.strip().startswith("OrderCreate_v6")


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _unwrap_serviceresponse(payload: Any) -> Any:
    """v6 logs wrap the payload: {"serviceresponse": {responsepreamble, ordersummary}}."""
    if isinstance(payload, dict):
        inner = payload.get("serviceresponse")
        if isinstance(inner, dict):
            return inner
    return payload


def extract_preamble(payload: Any) -> dict[str, Any] | None:
    payload = _unwrap_serviceresponse(payload)
    if not isinstance(payload, dict):
        return None
    preamble = payload.get("responsepreamble")
    if isinstance(preamble, dict):
        return preamble
    return None


_GLOBAL_ORDER_ID_KEYS = (
    "globalorderid",
    "globalOrderId",
    "invoicingsystemorderid",
    "ingramOrderNumber",
)


def extract_globalorderid(payload: Any) -> str:
    """Pull the impulse/global order id from a response payload.

    Handles the Datadog log shape (``ordersummary.ordercreateresponse[*]``,
    optionally wrapped in ``serviceresponse``) as well as REST-style bodies
    (``orders[*].ingramOrderNumber`` / camelCase keys). Every entry is checked;
    the first nonblank id wins, then summary-level keys are used as fallback.
    """
    payload = _unwrap_serviceresponse(payload)
    if not isinstance(payload, dict):
        return ""

    containers: list[dict[str, Any]] = []
    for key in ("ordersummary", "orderSummary"):
        summary = payload.get(key)
        if isinstance(summary, dict):
            containers.append(summary)
    containers.append(payload)

    for container in containers:
        entries: list[Any] = []
        for list_key in ("ordercreateresponse", "orders"):
            value = container.get(list_key)
            if isinstance(value, list):
                entries = value
                break

        for key in _GLOBAL_ORDER_ID_KEYS:
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                value = _as_str(entry.get(key))
                if value:
                    return value

        for key in _GLOBAL_ORDER_ID_KEYS:
            value = _as_str(container.get(key))
            if value:
                return value

    return ""


def find_globalorderid_in_records(records: list[dict[str, Any]]) -> str:
    """Scan all fetched records for an impulse/global order id.

    The id may live in a different log than the classified response (e.g. the
    OrderCreate_v2 XML response clubs orderBranchNumber-orderNumber).
    """
    for record in records:
        if not isinstance(record, dict):
            continue
        for key in ("ResponseLogPayload", "response"):
            value = extract_globalorderid(record.get(key))
            if value:
                return value

    for record in records:
        if not isinstance(record, dict):
            continue
        parsed = extract_v2_response_from_record(record)
        if parsed:
            impulse = _as_str(parsed.get("impulseOrderNumber"))
            if impulse:
                return impulse
    return ""


def classify_preamble(preamble: dict[str, Any]) -> Outcome:
    status = _as_str(preamble.get("responsestatus")).upper()
    code = _as_str(preamble.get("statuscode"))
    message = _as_str(preamble.get("responsemessage")).upper()
    errorcode = _as_str(preamble.get("errorcode"))

    if status == "SUCCESS" and code == "200" and message == "SUCCESS":
        if "errorcode" not in preamble or errorcode == "":
            return "SUCCESS"
        return "UNKNOWN"

    if status == "FAILED":
        return "FAILED"
    return "UNKNOWN"


def classify_v2_request_status(request_status: str, return_code: str) -> Outcome:
    status = _as_str(request_status).upper()
    code = _as_str(return_code)

    if status == "SUCCESS" or (
        status.startswith("S") and code in ("", "0", "00", "200")
    ):
        return "SUCCESS"
    if status in ("FAILED", "ERROR", "E"):
        return "FAILED"
    return "UNKNOWN"


def check_from_v2_xml(record: dict[str, Any]) -> ResponseCheckResult | None:
    """Build ResponseCheckResult from OrderCreate_v2_0 XML OrderCreate Response fields."""
    parsed = extract_v2_response_from_record(record)
    if parsed is None:
        return None

    request_status = parsed.get("requestStatus", "")
    return_code = parsed.get("returnCode", "")
    return_message = parsed.get("returnMessage", "")
    outcome = classify_v2_request_status(request_status, return_code)

    return ResponseCheckResult(
        outcome=outcome,
        statuscode=return_code,
        responsemessage=return_message,
        errorcode=return_code,
        responsestatus=request_status,
        globalorderid=parsed.get("impulseOrderNumber", ""),
        raw_preamble=parsed,
        response_payload={"v2xml": parsed},
        source_log_id=_as_str(record.get("log_id")) or None,
        customer_order_number=parsed.get("customerOrderNumber", ""),
        source_service=_as_str(record.get("service")),
    )


def find_response_check(records: list[dict[str, Any]]) -> ResponseCheckResult | None:
    """Prefer JSON responsepreamble; also accept OrderCreate_v2_0 XML responses.

    An OrderCreate_v6* response record ('OrderCreate Response formed') is
    always preferred when present. Within the chosen pool the preference is:
    FAILED with two-char statuscode, then any FAILED, then SUCCESS, else first.
    """
    candidates: list[ResponseCheckResult] = []
    for record in records:
        payload = record.get("ResponseLogPayload")
        if payload is None:
            payload = record.get("response")
        preamble = extract_preamble(payload)
        if preamble is not None:
            outcome = classify_preamble(preamble)
            payload_dict = payload if isinstance(payload, dict) else None
            candidates.append(
                ResponseCheckResult(
                    outcome=outcome,
                    statuscode=_as_str(preamble.get("statuscode")),
                    responsemessage=_as_str(preamble.get("responsemessage")),
                    errorcode=_as_str(preamble.get("errorcode")),
                    responsestatus=_as_str(preamble.get("responsestatus")),
                    globalorderid=extract_globalorderid(payload_dict),
                    raw_preamble=preamble,
                    response_payload=payload_dict,
                    source_log_id=_as_str(record.get("log_id")) or None,
                    source_service=_as_str(record.get("service")),
                )
            )
            continue

        xml_check = check_from_v2_xml(record)
        if xml_check is not None:
            candidates.append(xml_check)

    if not candidates:
        return None

    # v6 response records are authoritative when present.
    v6_candidates = [c for c in candidates if is_v6_response_service(c.source_service)]
    pool = v6_candidates or candidates

    failed = [c for c in pool if c.outcome == "FAILED"]
    if failed:
        for item in failed:
            if is_two_char_error_code(item.statuscode):
                return item
        # Non-two-char FAILED: try map from v2 XML statuscode across records
        mapped = map_two_char_from_v2_sources(records, failed[0])
        if mapped is not None:
            return mapped
        return failed[0]

    for item in pool:
        if item.outcome == "SUCCESS":
            return item
    return pool[0]


def map_two_char_from_v2_sources(
    records: list[dict[str, Any]],
    base: ResponseCheckResult,
) -> ResponseCheckResult | None:
    """If base.statuscode is not two-char, map from v2 XML ``statuscode`` / returnCode."""
    if is_two_char_error_code(base.statuscode):
        return None

    code = find_two_char_statuscode_in_sources(
        records=records,
        response_payload=base.response_payload,
    )
    if not code:
        return None

    return ResponseCheckResult(
        outcome=base.outcome,
        statuscode=code,
        responsemessage=base.responsemessage,
        errorcode=base.errorcode,
        responsestatus=base.responsestatus,
        globalorderid=base.globalorderid,
        raw_preamble={
            **(base.raw_preamble or {}),
            "originalStatuscode": base.statuscode,
            "mappedFromV2Statuscode": code,
        },
        response_payload=base.response_payload,
        source_log_id=base.source_log_id,
        customer_order_number=base.customer_order_number,
        source_service=base.source_service,
    )


def find_two_char_statuscode_in_sources(
    *,
    records: list[dict[str, Any]] | None = None,
    response_payload: dict[str, Any] | None = None,
    http_body: Any = None,
) -> str:
    """Find a two-char CORORA code from v2 XML ``statuscode`` (e.g. tns:statuscode)."""
    for text in _iter_source_strings(
        records=records, response_payload=response_payload, http_body=http_body
    ):
        code = extract_xml_statuscode(text)
        if is_two_char_error_code(code):
            return code.strip().upper()

        parsed = parse_v2_response_text(text)
        if parsed:
            for key in ("statuscode", "returnCode"):
                candidate = (parsed.get(key) or "").strip()
                if is_two_char_error_code(candidate):
                    return candidate.upper()

    # Structured v2xml / JSON records without raw XML text
    for record in records or []:
        parsed = extract_v2_response_from_record(record)
        if not parsed:
            continue
        for key in ("statuscode", "returnCode"):
            candidate = (parsed.get(key) or "").strip()
            if is_two_char_error_code(candidate):
                return candidate.upper()

    return ""


def _iter_source_strings(
    *,
    records: list[dict[str, Any]] | None = None,
    response_payload: dict[str, Any] | None = None,
    http_body: Any = None,
) -> list[str]:
    chunks: list[str] = []

    def _add(value: Any) -> None:
        if isinstance(value, str) and value.strip():
            chunks.append(value)
        elif isinstance(value, dict):
            for nested in value.values():
                if isinstance(nested, str) and nested.strip():
                    chunks.append(nested)

    _add(http_body)
    _add(response_payload)
    for record in records or []:
        if not isinstance(record, dict):
            continue
        for key in (
            "message",
            "response",
            "ResponseLogPayload",
            "request",
            "RequestLogPayload",
        ):
            _add(record.get(key))
    return chunks


def build_result_payload(
    *,
    outcome: str,
    customer_order_number: str,
    original_customer_order_number: str,
    source_search_text: str | None = None,
    statuscode: str = "",
    responsemessage: str = "",
    errorcode: str = "",
    responsestatus: str = "",
    globalorderid: str = "",
    http_status: int | None = None,
    source_log_id: str | None = None,
    response_payload: dict[str, Any] | None = None,
    http_body: Any = None,
    message: str | None = None,
) -> dict[str, Any]:
    """Canonical SUCCESS/FAILED/TIMEOUT/UNKNOWN result stored as order-create-result.json."""
    resolved_status = responsestatus
    if not resolved_status and outcome in ("SUCCESS", "FAILED"):
        resolved_status = outcome
    resolved_global = globalorderid or extract_globalorderid(response_payload)
    result: dict[str, Any] = {
        "sourceSearchText": source_search_text,
        "originalCustomerOrderNumber": original_customer_order_number,
        "customerOrderNumber": customer_order_number,
        "outcome": outcome,
        "responsestatus": resolved_status,
        "statuscode": statuscode,
        "responsemessage": responsemessage,
        "errorcode": errorcode,
        "globalorderid": resolved_global,
        "http_status": http_status,
        "fetched_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_log_id": source_log_id,
    }
    if response_payload is not None:
        result["ResponseLogPayload"] = response_payload
    if http_body is not None:
        result["http_body"] = http_body
    if message is not None:
        result["message"] = message
    return result


def build_error_report(
    *,
    customer_order_number: str,
    check: ResponseCheckResult,
    http_status: int | None = None,
    original_customer_order_number: str | None = None,
    source_search_text: str | None = None,
) -> dict[str, Any]:
    return build_result_payload(
        outcome="FAILED",
        customer_order_number=customer_order_number,
        original_customer_order_number=original_customer_order_number
        or customer_order_number,
        source_search_text=source_search_text,
        statuscode=check.statuscode,
        responsemessage=check.responsemessage,
        errorcode=check.errorcode,
        responsestatus=check.responsestatus or "FAILED",
        globalorderid=check.globalorderid,
        http_status=http_status,
        source_log_id=check.source_log_id,
        response_payload=check.response_payload,
    )


def build_success_summary(
    *,
    customer_order_number: str,
    check: ResponseCheckResult,
    http_status: int | None = None,
    original_customer_order_number: str | None = None,
    source_search_text: str | None = None,
) -> dict[str, Any]:
    return build_result_payload(
        outcome="SUCCESS",
        customer_order_number=customer_order_number,
        original_customer_order_number=original_customer_order_number
        or customer_order_number,
        source_search_text=source_search_text,
        statuscode=check.statuscode,
        responsemessage=check.responsemessage,
        errorcode=check.errorcode,
        responsestatus=check.responsestatus or "SUCCESS",
        globalorderid=check.globalorderid,
        http_status=http_status,
        source_log_id=check.source_log_id,
        response_payload=check.response_payload,
    )
