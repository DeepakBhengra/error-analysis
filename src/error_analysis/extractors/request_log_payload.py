from __future__ import annotations

import json
import re
from typing import Any

DEFAULT_PAYLOAD_PATHS = [
    "attributes.attributes.RequestLogPayload",
    "attributes.RequestLogPayload",
    "RequestLogPayload",
]

# Prefix-tolerant XML tags, e.g. <pfx5:JobID>abc</pfx5:JobID> or <JobID>abc</JobID>
_JOB_ID_RE = re.compile(
    r"<(?:\w+:)?JobID>(.*?)</(?:\w+:)?JobID>",
    re.IGNORECASE | re.DOTALL,
)
_CORRELATION_ID_RE = re.compile(
    r"<(?:\w+:)?CorrelationID>(.*?)</(?:\w+:)?CorrelationID>",
    re.IGNORECASE | re.DOTALL,
)

_JOB_ID_ATTR_KEYS = ("JobID", "jobId", "job_id", "JobId")
_CORRELATION_ID_ATTR_KEYS = (
    "CorrelationID",
    "correlationId",
    "correlation_id",
    "IM-CorrelationID",
    "IM-CORRELATIONID",
)


def _get_by_path(data: dict[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _parse_json_value(value: Any) -> Any | None:
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return None
    return None


def _extract_balanced_json(message: str, start: int) -> Any | None:
    """Brace-match a JSON object beginning at ``message[start] == '{'``."""
    depth = 0
    in_string = False
    escape = False
    for j in range(start, len(message)):
        ch = message[j]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return _parse_json_value(message[start : j + 1])
    return None


def _extract_json_object_after_key(message: str, key: str) -> Any | None:
    """Extract a JSON object that follows \"key\": in a possibly XML-wrapped message."""
    marker = f'"{key}"'
    start = message.find(marker)
    if start < 0:
        return None
    colon = message.find(":", start + len(marker))
    if colon < 0:
        return None
    i = colon + 1
    while i < len(message) and message[i].isspace():
        i += 1
    if i >= len(message) or message[i] != "{":
        return None
    return _extract_balanced_json(message, i)


# TIBCO logs wrap the JSON payload in an XML tag, e.g.
# <pfx5:RequestLogPayload>OMP URI : /API/...&#xD; {"ordercreaterequest": ...}
_XML_PAYLOAD_TAG_RES: dict[str, re.Pattern[str]] = {}


def _xml_payload_tag_re(tag: str) -> re.Pattern[str]:
    pattern = _XML_PAYLOAD_TAG_RES.get(tag)
    if pattern is None:
        pattern = re.compile(rf"<(?:\w+:)?{re.escape(tag)}>", re.IGNORECASE)
        _XML_PAYLOAD_TAG_RES[tag] = pattern
    return pattern


def extract_json_after_xml_tag(
    message: str,
    tag: str = "RequestLogPayload",
) -> Any | None:
    """Extract the JSON object inside an XML payload tag (prefix-tolerant)."""
    match = _xml_payload_tag_re(tag).search(message)
    if not match:
        return None
    brace = message.find("{", match.end())
    if brace < 0:
        return None
    closing = message.find("</", match.end())
    if 0 <= closing < brace:
        # The tag closed before any JSON object started.
        return None
    return _extract_balanced_json(message, brace)


def _extract_json_after_xml_tag(message: str) -> Any | None:
    return extract_json_after_xml_tag(message, "RequestLogPayload")


def _extract_from_message(message: str) -> Any | None:
    if not message:
        return None

    # Try full message as JSON
    parsed = _parse_json_value(message)
    if isinstance(parsed, dict) and "RequestLogPayload" in parsed:
        return parsed["RequestLogPayload"]

    embedded = _extract_json_object_after_key(message, "RequestLogPayload")
    if embedded is not None:
        return embedded

    tagged = _extract_json_after_xml_tag(message)
    if tagged is not None:
        return tagged

    # Fallback: looser regex (may fail on nested braces)
    match = re.search(
        r'"RequestLogPayload"\s*:\s*(\{.*\}|\[.*\])',
        message,
        re.DOTALL,
    )
    if match:
        return _parse_json_value(match.group(1))

    return None


def _extract_tagged_id(
    log_event: dict[str, Any],
    *,
    attr_keys: tuple[str, ...],
    xml_re: re.Pattern[str],
) -> str | None:
    attributes = log_event.get("attributes") or {}
    nested_attrs = attributes.get("attributes") or {}
    for container in (nested_attrs, attributes, log_event):
        if not isinstance(container, dict):
            continue
        for key in attr_keys:
            value = container.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    message = attributes.get("message", "")
    if isinstance(message, str) and message:
        match = xml_re.search(message)
        if match:
            value = match.group(1).strip()
            if value:
                return value
    return None


def extract_job_id(log_event: dict[str, Any]) -> str | None:
    """Extract JobID from nested attributes or an XML-wrapped log message."""
    return _extract_tagged_id(
        log_event, attr_keys=_JOB_ID_ATTR_KEYS, xml_re=_JOB_ID_RE
    )


def extract_correlation_id(log_event: dict[str, Any]) -> str | None:
    """Extract CorrelationID from nested attributes or an XML-wrapped log message."""
    return _extract_tagged_id(
        log_event,
        attr_keys=_CORRELATION_ID_ATTR_KEYS,
        xml_re=_CORRELATION_ID_RE,
    )


def extract_request_log_payload(
    log_event: dict[str, Any],
    payload_path: str | None = None,
) -> Any | None:
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
    for key in ("RequestLogPayload", "@RequestLogPayload"):
        if key in nested_attrs:
            parsed = _parse_json_value(nested_attrs[key])
            if parsed is not None:
                return parsed

    message = attributes.get("message", "")
    if isinstance(message, str):
        return _extract_from_message(message)

    return None


def build_result_record(
    log_event: dict[str, Any],
    payload: Any,
) -> dict[str, Any]:
    attributes = log_event.get("attributes") or {}
    return {
        "log_id": log_event.get("id"),
        "timestamp": attributes.get("timestamp"),
        "host": attributes.get("host"),
        "service": attributes.get("service"),
        "request_log_payload": payload,
    }
