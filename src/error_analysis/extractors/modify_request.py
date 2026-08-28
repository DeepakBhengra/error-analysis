from __future__ import annotations

import re
from typing import Any

from error_analysis.extractors.request_payload import extract_request_payload

MODIFY_SERVICE_PREFIX = "OrderModify_v6"

_REQUEST_ATTR_KEYS = (
    "RequestPayload",
    "requestPayload",
)

_ORDER_ID_IN_MESSAGE_RE = re.compile(
    r"/resellers/v6/orders/(\d+-\d+-\d+)",
    re.IGNORECASE,
)


def _is_modify_service(service: Any) -> bool:
    return isinstance(service, str) and service.startswith(MODIFY_SERVICE_PREFIX)


def is_order_modify_body(payload: Any) -> bool:
    """True when payload looks like an Order Modify v6 request body."""
    if not isinstance(payload, dict):
        return False
    if not isinstance(payload.get("customerOrderNumber"), str):
        return False
    lines = payload.get("lines")
    return isinstance(lines, list)


def extract_modify_request(log_event: dict[str, Any]) -> Any | None:
    """Extract Order Modify request JSON from a log event."""
    attributes = log_event.get("attributes") or {}
    service = attributes.get("service")
    nested = attributes.get("attributes") or {}

    for key in _REQUEST_ATTR_KEYS:
        for container in (nested, attributes, log_event):
            if not isinstance(container, dict) or key not in container:
                continue
            value = container[key]
            if isinstance(value, dict) and is_order_modify_body(value):
                return value
            if isinstance(value, str) and value.strip():
                from error_analysis.extractors.request_log_payload import (
                    _parse_json_value,
                )

                parsed = _parse_json_value(value)
                if isinstance(parsed, dict) and is_order_modify_body(parsed):
                    return parsed

    payload = extract_request_payload(log_event)
    if isinstance(payload, dict) and is_order_modify_body(payload):
        return payload

    # Only accept free-text JSON on modify services to avoid misclassifying creates.
    if _is_modify_service(service):
        message = attributes.get("message", "")
        if isinstance(message, str) and message.strip():
            payload = extract_request_payload({"attributes": {"message": message}})
            if isinstance(payload, dict) and is_order_modify_body(payload):
                return payload

    return None


def extract_order_id_from_message(log_event: dict[str, Any]) -> str | None:
    """Extract Ingram order id from a log message URI (/orders/29-44694-11)."""
    attributes = log_event.get("attributes") or {}
    message = attributes.get("message", "")
    if not isinstance(message, str) or not message.strip():
        return None
    match = _ORDER_ID_IN_MESSAGE_RE.search(message)
    if match:
        return match.group(1).strip()
    return None
