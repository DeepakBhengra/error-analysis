from __future__ import annotations

import re
from typing import Any

V2_SERVICE_NAME = "OrderCreate_v2_0"
ORDER_CREATE_RESPONSE_MARKER = "OrderCreate Response"

_TAG_RE_CACHE: dict[str, re.Pattern[str]] = {}


def _tag_re(name: str) -> re.Pattern[str]:
    """Prefix-tolerant XML tag regex, e.g. <pfx5:returnCode>...</pfx5:returnCode>."""
    cached = _TAG_RE_CACHE.get(name)
    if cached is not None:
        return cached
    pattern = re.compile(
        rf"<(?:\w+:)?{re.escape(name)}>(.*?)</(?:\w+:)?{re.escape(name)}>",
        re.IGNORECASE | re.DOTALL,
    )
    _TAG_RE_CACHE[name] = pattern
    return pattern


def _xml_tag_value(text: str, name: str) -> str:
    match = _tag_re(name).search(text)
    if not match:
        return ""
    return match.group(1).strip()


def club_impulse_order_number(branch: str, number: str) -> str:
    """Club orderBranchNumber and orderNumber into Impulse Order Number."""
    branch = (branch or "").strip()
    number = (number or "").strip()
    if branch and number:
        return f"{branch}-{number}"
    return branch or number


def _raw_attr_strings(log_event: dict[str, Any]) -> list[str]:
    """Collect string attribute values that may hold XML (not JSON-parsed)."""
    attributes = log_event.get("attributes") or {}
    nested = attributes.get("attributes") if isinstance(attributes, dict) else None
    keys = (
        "RequestLogPayload",
        "requestLogPayload",
        "ResponseLogPayload",
        "responseLogPayload",
        "message",
    )
    chunks: list[str] = []
    for container in (nested, attributes, log_event):
        if not isinstance(container, dict):
            continue
        for key in keys:
            value = container.get(key)
            if isinstance(value, str) and value.strip():
                chunks.append(value)
    return chunks


def _source_text(log_event: dict[str, Any]) -> str:
    return "\n".join(_raw_attr_strings(log_event))


def is_v2_order_create_response(text: str) -> bool:
    if not text:
        return False
    has_preamble_style = bool(
        _xml_tag_value(text, "statuscode") or _xml_tag_value(text, "responsestatus")
    )
    has_classic = bool(
        _xml_tag_value(text, "requestStatus") or _xml_tag_value(text, "returnCode")
    )
    if not (has_preamble_style or has_classic):
        return False

    # Classic OrderCreate_v2_0 responses include the service marker.
    if ORDER_CREATE_RESPONSE_MARKER.lower() in text.lower():
        service = _xml_tag_value(text, "ServiceName")
        if V2_SERVICE_NAME in service or V2_SERVICE_NAME in text:
            return True

    # Preamble-style SOAP fragments (e.g. tns:statuscode) are accepted even
    # when ServiceName is absent.
    return has_preamble_style


_PREAMBLE_BLOCK_RE = re.compile(
    r"<(?:\w+:)?responsepreamble>(.*?)</(?:\w+:)?responsepreamble>",
    re.IGNORECASE | re.DOTALL,
)


def _pick_preamble_block(text: str) -> str | None:
    """Pick the responsepreamble XML block; prefer a FAILED one when several exist.

    A single v2 response can carry both a warning-level SUCCESS fragment and a
    FAILED responsepreamble (e.g. statuscode D9 NO-ADDR-SEQ); FAILED must win.
    """
    blocks = _PREAMBLE_BLOCK_RE.findall(text)
    if not blocks:
        return None
    for block in blocks:
        if _xml_tag_value(block, "responsestatus").upper() == "FAILED":
            return block
    return blocks[0]


def parse_v2_response_text(text: str) -> dict[str, str] | None:
    """Parse OrderCreate_v2_0 OrderCreate Response XML into a normalized dict.

    Supports classic v2 tags (requestStatus/returnCode/returnMessage) and
    preamble-style tags (responsestatus/statuscode/responsemessage), including
    namespace prefixes such as ``tns:statuscode``.
    """
    if not is_v2_order_create_response(text):
        return None

    branch = _xml_tag_value(text, "orderBranchNumber")
    number = _xml_tag_value(text, "orderNumber")
    request_status = _xml_tag_value(text, "requestStatus")
    return_code = _xml_tag_value(text, "returnCode")
    return_message = _xml_tag_value(text, "returnMessage")

    # Preamble tags: scope to the responsepreamble block (preferring FAILED)
    # so warning-level fragments elsewhere in the log cannot mask an error.
    preamble_block = _pick_preamble_block(text)
    scope = preamble_block if preamble_block is not None else text
    responsestatus = _xml_tag_value(scope, "responsestatus")
    statuscode = _xml_tag_value(scope, "statuscode")
    responsemessage = _xml_tag_value(scope, "responsemessage")

    # Prefer preamble-style tags when present; fall back to classic v2 names.
    resolved_status = responsestatus or request_status
    resolved_code = statuscode or return_code
    resolved_message = responsemessage or return_message

    return {
        "requestStatus": resolved_status,
        "returnCode": resolved_code,
        "returnMessage": resolved_message,
        "responsestatus": responsestatus,
        "statuscode": statuscode,
        "responsemessage": responsemessage,
        "orderBranchNumber": branch,
        "orderNumber": number,
        "customerOrderNumber": _xml_tag_value(text, "customerOrderNumber"),
        "impulseOrderNumber": club_impulse_order_number(branch, number),
        "serviceName": _xml_tag_value(text, "ServiceName") or V2_SERVICE_NAME,
    }


def extract_xml_statuscode(text: str) -> str:
    """Return ``<tns:statuscode>`` / ``<statuscode>`` value from XML text, if any."""
    if not text or not isinstance(text, str):
        return ""
    return _xml_tag_value(text, "statuscode")


def extract_v2_response(log_event: dict[str, Any]) -> dict[str, str] | None:
    """Extract OrderCreate_v2_0 XML OrderCreate Response from a Datadog log event."""
    text = _source_text(log_event)
    return parse_v2_response_text(text)


def extract_v2_response_from_record(record: dict[str, Any]) -> dict[str, str] | None:
    """Extract v2 XML response from a fetch-request record (or embedded v2xml dict)."""
    for key in ("response", "ResponseLogPayload", "request", "RequestLogPayload"):
        value = record.get(key)
        if isinstance(value, dict):
            nested = value.get("v2xml")
            if isinstance(nested, dict) and (
                nested.get("requestStatus")
                or nested.get("returnCode")
                or nested.get("statuscode")
                or nested.get("responsestatus")
            ):
                return _normalize_v2_dict(nested)
            # Already-normalized flat dict
            if (
                value.get("requestStatus")
                or value.get("returnCode")
                or value.get("statuscode")
                or value.get("responsestatus")
            ):
                if (
                    value.get("impulseOrderNumber") is not None
                    or value.get("returnMessage") is not None
                    or value.get("responsemessage") is not None
                    or value.get("statuscode") is not None
                ):
                    return _normalize_v2_dict(value)
        if isinstance(value, str):
            parsed = parse_v2_response_text(value)
            if parsed is not None:
                return parsed

    message = record.get("message")
    if isinstance(message, str):
        return parse_v2_response_text(message)
    return None


def _normalize_v2_dict(value: dict[str, Any]) -> dict[str, str]:
    branch = str(value.get("orderBranchNumber") or "").strip()
    number = str(value.get("orderNumber") or "").strip()
    responsestatus = str(value.get("responsestatus") or "").strip()
    statuscode = str(value.get("statuscode") or "").strip()
    responsemessage = str(value.get("responsemessage") or "").strip()
    request_status = str(value.get("requestStatus") or "").strip()
    return_code = str(value.get("returnCode") or "").strip()
    return_message = str(value.get("returnMessage") or "").strip()
    resolved_status = responsestatus or request_status
    resolved_code = statuscode or return_code
    resolved_message = responsemessage or return_message
    return {
        "requestStatus": resolved_status,
        "returnCode": resolved_code,
        "returnMessage": resolved_message,
        "responsestatus": responsestatus,
        "statuscode": statuscode,
        "responsemessage": responsemessage,
        "orderBranchNumber": branch,
        "orderNumber": number,
        "customerOrderNumber": str(value.get("customerOrderNumber") or "").strip(),
        "impulseOrderNumber": str(
            value.get("impulseOrderNumber")
            or club_impulse_order_number(branch, number)
        ).strip(),
        "serviceName": str(value.get("serviceName") or V2_SERVICE_NAME).strip(),
    }
