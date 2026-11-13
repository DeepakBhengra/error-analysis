"""Extract Order Create SOAP XML from APPPCG-Identity Datadog logs."""

from __future__ import annotations

import re
from typing import Any

XML_ORDER_CREATE_SERVICE = "APPPCG-Identity"
XML_ORDER_CREATE_PATH = "/Processes/OrderCreate/OrderCreate_v1_0"

_CREDENTIAL_RE = re.compile(
    r"(<credential>)(.*?)(</credential>)",
    re.IGNORECASE | re.DOTALL,
)
_CUSTOMER_ORDER_RE = re.compile(
    r"<customerOrderNumber>\s*(.*?)\s*</customerOrderNumber>",
    re.IGNORECASE | re.DOTALL,
)
_SOAP_ENVELOPE_RE = re.compile(
    r"<(?:\w+:)?Envelope\b",
    re.IGNORECASE,
)


def redact_xml_credentials(xml: str) -> str:
    """Mask SOAP ``<credential>`` values before returning XML to the UI."""
    return _CREDENTIAL_RE.sub(r"\1***\3", xml)


_TAG_SPLIT_RE = re.compile(r"(<[^>]+>)")


def format_order_create_xml(xml: str, *, indent: str = "  ") -> str:
    """Pretty-print SOAP XML for the XML request tab.

    Uses tag tokens so namespace prefixes and leaf text stay intact. Empty or
    unparseable input is returned unchanged.
    """
    text = xml.strip()
    if not text or "<" not in text:
        return xml
    compact = re.sub(r">\s+<", "><", text)
    tokens = [part for part in _TAG_SPLIT_RE.split(compact) if part != ""]
    depth = 0
    lines: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        pad = indent * depth
        if token.startswith("</"):
            depth = max(depth - 1, 0)
            pad = indent * depth
            lines.append(f"{pad}{token}")
            index += 1
            continue
        if token.startswith("<?") or token.startswith("<!"):
            lines.append(f"{pad}{token}")
            index += 1
            continue
        if token.startswith("<") and token.endswith("/>"):
            lines.append(f"{pad}{token}")
            index += 1
            continue
        if token.startswith("<"):
            nxt = tokens[index + 1] if index + 1 < len(tokens) else ""
            nxt2 = tokens[index + 2] if index + 2 < len(tokens) else ""
            if nxt.startswith("</"):
                lines.append(f"{pad}{token}{nxt}")
                index += 2
                continue
            if not nxt.startswith("<") and nxt2.startswith("</"):
                lines.append(f"{pad}{token}{nxt}{nxt2}")
                index += 3
                continue
            lines.append(f"{pad}{token}")
            depth += 1
            index += 1
            continue
        stripped = token.strip()
        if stripped:
            lines.append(f"{pad}{stripped}")
        index += 1
    formatted = "\n".join(lines)
    return formatted + ("\n" if formatted else "")


def extract_customer_order_number(xml: str) -> str:
    match = _CUSTOMER_ORDER_RE.search(xml)
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(1)).strip()


def _nested_attributes(log_event: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    attributes = log_event.get("attributes") if isinstance(log_event.get("attributes"), dict) else {}
    nested = attributes.get("attributes") if isinstance(attributes.get("attributes"), dict) else {}
    return attributes, nested


def extract_http_url(log_event: dict[str, Any]) -> str:
    attributes, nested = _nested_attributes(log_event)
    for container in (nested, attributes, log_event):
        http = container.get("http") if isinstance(container, dict) else None
        if not isinstance(http, dict):
            continue
        url = http.get("url")
        if isinstance(url, str) and url.strip():
            return url.strip()
    return ""


def extract_http_path(log_event: dict[str, Any]) -> str:
    attributes, nested = _nested_attributes(log_event)
    for container in (nested, attributes, log_event):
        http = container.get("http") if isinstance(container, dict) else None
        if not isinstance(http, dict):
            continue
        details = http.get("url_details") if isinstance(http.get("url_details"), dict) else {}
        path = details.get("path")
        if isinstance(path, str) and path.strip():
            return path.strip()
    url = extract_http_url(log_event)
    if "://" in url:
        without_host = url.split("://", 1)[1]
        slash = without_host.find("/")
        if slash >= 0:
            return without_host[slash:].split("?", 1)[0]
    return ""


def is_order_create_xml_event(log_event: dict[str, Any]) -> bool:
    """True when the log is APPPCG-Identity OrderCreate_v1_0."""
    attributes, nested = _nested_attributes(log_event)
    service = str(attributes.get("service") or nested.get("service") or "").strip()
    if service != XML_ORDER_CREATE_SERVICE:
        return False
    path = extract_http_path(log_event)
    url = extract_http_url(log_event)
    soapaction = str(nested.get("soapaction") or attributes.get("soapaction") or "")
    haystack = f"{path} {url} {soapaction}"
    return XML_ORDER_CREATE_PATH.lower() in haystack.lower()


def _looks_like_order_create_soap(value: str) -> bool:
    stripped = value.strip()
    if not stripped or not _SOAP_ENVELOPE_RE.search(stripped):
        return False
    lowered = stripped.lower()
    return "ordercreaterequest" in lowered or "ordercreate" in lowered


def extract_order_create_xml(log_event: dict[str, Any]) -> str | None:
    """Return the SOAP Order Create request from the Datadog ``request`` attribute."""
    attributes, nested = _nested_attributes(log_event)
    for container in (nested, attributes, log_event):
        if not isinstance(container, dict):
            continue
        request = container.get("request")
        if isinstance(request, str) and _looks_like_order_create_soap(request):
            return format_order_create_xml(redact_xml_credentials(request.strip()))
    return None
