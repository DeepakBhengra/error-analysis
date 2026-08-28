from __future__ import annotations

import json
import re
from typing import Any

DEFAULT_PAYLOAD_PATHS = [
    "attributes.attributes.RequestPayload",
    "attributes.RequestPayload",
    "RequestPayload",
]

from error_analysis.extractors.request_log_payload import (
    _extract_json_object_after_key,
    _get_by_path,
    _parse_json_value,
    extract_json_after_xml_tag,
)

_MODIFY_PAYLOAD_TAG = "RequestPayload"


def _extract_from_message(message: str) -> Any | None:
    if not message:
        return None

    parsed = _parse_json_value(message)
    if isinstance(parsed, dict) and "RequestPayload" in parsed:
        return parsed["RequestPayload"]

    embedded = _extract_json_object_after_key(message, "RequestPayload")
    if embedded is not None:
        return embedded

    tagged = extract_json_after_xml_tag(message, _MODIFY_PAYLOAD_TAG)
    if tagged is not None:
        return tagged

    match = re.search(
        r'"RequestPayload"\s*:\s*(\{.*\}|\[.*\])',
        message,
        re.DOTALL,
    )
    if match:
        return _parse_json_value(match.group(1))

    return None


def extract_request_payload(
    log_event: dict[str, Any],
    payload_path: str | None = None,
) -> Any | None:
    """Extract Order Modify ``RequestPayload`` from a Datadog log event."""
    paths = [payload_path] if payload_path else DEFAULT_PAYLOAD_PATHS

    for path in paths:
        if not path:
            continue
        value = _get_by_path(log_event, path)
        parsed = _parse_json_value(value)
        if parsed is not None:
            return parsed

    attributes = log_event.get("attributes") or {}
    nested_attrs = attributes.get("attributes") or {}
    for key in ("RequestPayload", "@RequestPayload", "requestPayload"):
        if key in nested_attrs:
            parsed = _parse_json_value(nested_attrs[key])
            if parsed is not None:
                return parsed

    message = attributes.get("message", "")
    if isinstance(message, str):
        return _extract_from_message(message)

    return None
