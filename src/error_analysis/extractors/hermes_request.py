from __future__ import annotations

import json
import re
from typing import Any

HERMES_REQUEST_PREFIXES = (
    "Error in Hermes Order Simulate: Request :",
    "Error in Hermes Order Simulate: Request:",
)

HERMES_RESPONSE_PREFIXES = (
    "Error in Hermes Order Simulate: Response :",
    "Error in Hermes Order Simulate: Response:",
    "Hermes Order Simulate: Response :",
    "Hermes Order Simulate: Response:",
)

REQUEST_ATTR_KEYS = (
    "RequestLogPayload",
    "requestLogPayload",
    "servicerequest",
)

RESPONSE_ATTR_KEYS = (
    "ResponseLogPayload",
    "responseLogPayload",
    "serviceresponse",
)

MESSAGE_JSON_RE = re.compile(r"(\{.*\})", re.DOTALL)


def _parse_json(text: str) -> Any | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _parse_json_value(value: Any) -> Any | None:
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        return _parse_json(value.strip()) if value.strip() else None
    return None


def _get_nested_attr(log_event: dict[str, Any], key: str) -> Any | None:
    attributes = log_event.get("attributes") or {}
    nested = attributes.get("attributes") or {}
    for container in (nested, attributes, log_event):
        if isinstance(container, dict) and key in container:
            return _parse_json_value(container[key])
    return None


def _strip_prefix(message: str, prefixes: tuple[str, ...]) -> str | None:
    text = message.strip()
    for prefix in prefixes:
        if text.startswith(prefix):
            return text[len(prefix) :].strip()
    return None


def _extract_keyed_payload(parsed: Any, keys: tuple[str, ...]) -> Any | None:
    if not isinstance(parsed, dict):
        return None
    for key in keys:
        if key in parsed:
            return parsed[key]
    lower_map = {str(k).lower(): v for k, v in parsed.items()}
    for key in keys:
        if key.lower() in lower_map:
            return lower_map[key.lower()]
    return None


def _extract_from_message(
    message: str,
    prefixes: tuple[str, ...],
    keys: tuple[str, ...],
) -> Any | None:
    if not isinstance(message, str) or not message.strip():
        return None

    stripped = _strip_prefix(message, prefixes)
    candidates = [stripped] if stripped is not None else []

    match = MESSAGE_JSON_RE.search(message)
    if match:
        candidates.append(match.group(1))
    candidates.append(message.strip())

    for candidate in candidates:
        if not candidate:
            continue
        parsed = _parse_json(candidate)
        if parsed is None:
            continue
        keyed = _extract_keyed_payload(parsed, keys)
        if keyed is not None:
            return keyed
        # Message after Hermes request/response prefix is the payload itself
        if stripped is not None and candidate == stripped:
            return parsed
    return None


def extract_hermes_request(log_event: dict[str, Any]) -> Any | None:
    """Extract request / RequestLogPayload from a log event."""
    for key in REQUEST_ATTR_KEYS:
        value = _get_nested_attr(log_event, key)
        if value is not None:
            return value

    attributes = log_event.get("attributes") or {}
    message = attributes.get("message", "")
    if not isinstance(message, str) or not message.strip():
        return None

    # Prefer explicit Hermes request messages / RequestLogPayload keys
    from_message = _extract_from_message(
        message, HERMES_REQUEST_PREFIXES, REQUEST_ATTR_KEYS
    )
    if from_message is not None:
        return from_message

    # Do not treat response messages as requests
    if _strip_prefix(message, HERMES_RESPONSE_PREFIXES) is not None:
        return None
    if _extract_keyed_payload(_parse_json(message.strip()) or {}, RESPONSE_ATTR_KEYS):
        return None
    match = MESSAGE_JSON_RE.search(message)
    if match:
        parsed = _parse_json(match.group(1))
        if parsed is not None:
            if _extract_keyed_payload(parsed, RESPONSE_ATTR_KEYS) is not None:
                return None
            keyed = _extract_keyed_payload(parsed, REQUEST_ATTR_KEYS)
            if keyed is not None:
                return keyed
            # Free-text matching often surfaces request bodies embedded in the message
            return parsed

    # TIBCO / XML messages often embed RequestLogPayload JSON
    from error_analysis.extractors.request_log_payload import extract_request_log_payload

    return extract_request_log_payload(log_event)


def extract_hermes_response(log_event: dict[str, Any]) -> Any | None:
    """Extract response / ResponseLogPayload from a log event."""
    for key in RESPONSE_ATTR_KEYS:
        value = _get_nested_attr(log_event, key)
        if value is not None:
            return value

    attributes = log_event.get("attributes") or {}
    message = attributes.get("message", "")
    from_message = _extract_from_message(
        message, HERMES_RESPONSE_PREFIXES, RESPONSE_ATTR_KEYS
    )
    if from_message is not None:
        return from_message

    # TIBCO / XML messages embed the JSON in <pfx5:ResponseLogPayload>...</...>,
    # possibly with leading text and noise braces elsewhere in the XML.
    if isinstance(message, str) and message.strip():
        from error_analysis.extractors.request_log_payload import (
            extract_json_after_xml_tag,
        )

        tagged = extract_json_after_xml_tag(message, "ResponseLogPayload")
        if tagged is not None:
            keyed = _extract_keyed_payload(tagged, RESPONSE_ATTR_KEYS)
            return keyed if keyed is not None else tagged

    # OrderCreate_v2_0 XML "OrderCreate Response" (often on RequestLogPayload / message)
    from error_analysis.extractors.order_create_v2_response import extract_v2_response

    v2 = extract_v2_response(log_event)
    if v2 is not None:
        return {"v2xml": v2}
    return None


def extract_log_payloads(log_event: dict[str, Any]) -> tuple[Any | None, Any | None]:
    """Return (request_payload, response_payload) for a log event."""
    request = extract_hermes_request(log_event)
    response = extract_hermes_response(log_event)
    return request, response


def build_fetch_request_record(
    log_event: dict[str, Any],
    request: Any | None = None,
    response: Any | None = None,
    *,
    search_text: str | None = None,
    correlation_id: str | None = None,
    job_id: str | None = None,
    customer_po: str | None = None,
    env: str = "",
) -> dict[str, Any]:
    attributes = log_event.get("attributes") or {}
    return {
        "log_id": log_event.get("id"),
        "timestamp": attributes.get("timestamp"),
        "host": attributes.get("host"),
        "service": attributes.get("service"),
        "env": env,
        "search_text": search_text,
        "correlation_id": correlation_id,
        "job_id": job_id,
        "customer_po": customer_po,
        "request": request,
        "response": response,
        "RequestLogPayload": request,
        "ResponseLogPayload": response,
    }
