from __future__ import annotations

import base64
import json
import re
import uuid
from dataclasses import dataclass
from typing import Any

from error_analysis.extractors.modify_request import (
    MODIFY_SERVICE_PREFIX,
    extract_order_id_from_message,
    is_order_modify_body,
)
from error_analysis.order_create.curl_builder import (
    OrderCreateCurlError,
    build_order_create_headers,
    find_any_v2_header_record,
)
from error_analysis.order_create.response_check import (
    extract_globalorderid,
    find_globalorderid_in_records,
)

TEST_ORDERS_URL = (
    "https://api-test.ingrammicro.com:443/resellers/v6/orders"
)
QA1_ORDERS_URL = (
    "https://api-qa1.ingrammicro.com:443/resellers/v6/orders"
)

TARGET_URLS: dict[str, str] = {
    "test": TEST_ORDERS_URL,
    "qa1": QA1_ORDERS_URL,
}

_IM_HEADER_IN_MESSAGE_RE = re.compile(
    r"IM-(?:CountryCode|CustomerNumber|CorrelationId|CorrelationID|SenderID)\s*:\s*[^\s\\]+",
    re.IGNORECASE,
)
_XML_COUNTRY_RE = re.compile(
    r"<(?:\w+:)?CountryCode>(.*?)</(?:\w+:)?CountryCode>",
    re.IGNORECASE | re.DOTALL,
)
_XML_CUSTOMER_RE = re.compile(
    r"<(?:\w+:)?CustomerNumber>(.*?)</(?:\w+:)?CustomerNumber>",
    re.IGNORECASE | re.DOTALL,
)
_XML_CORRELATION_RE = re.compile(
    r"<(?:\w+:)?CorrelationId>(.*?)</(?:\w+:)?CorrelationId>",
    re.IGNORECASE | re.DOTALL,
)


class OrderModifyCurlError(ValueError):
    """Raised when a Datadog record cannot be turned into an Order Modify curl."""


@dataclass(frozen=True)
class OrderModifyCurl:
    url: str
    headers: dict[str, str]
    body: dict[str, Any]
    username: str
    curl: str
    order_id: str
    body_service: str = ""
    body_host: str = ""
    target: str = "test"


def normalize_order_modify_target(target: str | None) -> str:
    normalized = (target or "test").strip().lower() or "test"
    if normalized not in TARGET_URLS:
        raise OrderModifyCurlError(
            f"Unsupported target {target!r}. Expected one of: "
            f"{', '.join(sorted(TARGET_URLS))}."
        )
    return normalized


def resolve_order_modify_url(
    order_id: str,
    *,
    target: str | None = None,
) -> str:
    normalized_target = normalize_order_modify_target(target)
    cleaned_id = order_id.strip()
    if not cleaned_id:
        raise OrderModifyCurlError(
            "Ingram order id is required for Order Modify URL "
            "(e.g. 29-44694-11 from globalorderid or log URI)."
        )
    base = TARGET_URLS[normalized_target]
    return f"{base}/{cleaned_id}"


def _shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def _basic_auth_header(username: str, password: str, *, redact: bool) -> str:
    if redact:
        return "Basic ***"
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _headers_from_im_message(message: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for match in _IM_HEADER_IN_MESSAGE_RE.finditer(message):
        part = match.group(0)
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key.lower() == "im-correlationid":
            headers["IM-CorrelationId"] = value
        else:
            headers[key] = value
    return headers


def _record_correlation_id(record: dict[str, Any] | None) -> str | None:
    if not isinstance(record, dict):
        return None
    value = record.get("correlation_id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _resolve_order_id(records: list[dict[str, Any]], body_record: dict[str, Any]) -> str:
    for record in records:
        order_id = extract_order_id_from_message(record)
        if order_id:
            return order_id
        message = record.get("message")
        if isinstance(message, str) and message.strip():
            order_id = extract_order_id_from_message({"message": message})
            if order_id:
                return order_id

    from_response = find_globalorderid_in_records(records)
    if from_response:
        return from_response

    for record in records:
        for key in ("response", "ResponseLogPayload"):
            value = extract_globalorderid(record.get(key))
            if value:
                return value

    request = body_record.get("request")
    if isinstance(request, dict):
        for key in ("ingramOrderNumber", "globalorderid", "globalOrderId"):
            value = request.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    raise OrderModifyCurlError(
        "Could not resolve Ingram order id for Order Modify URL. "
        "Expected globalorderid/ingramOrderNumber in sibling logs or "
        "/resellers/v6/orders/{orderId} in the log message."
    )


def _headers_from_xml_log_message(message: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for pattern, key in (
        (_XML_COUNTRY_RE, "IM-CountryCode"),
        (_XML_CUSTOMER_RE, "IM-CustomerNumber"),
        (_XML_CORRELATION_RE, "IM-CorrelationId"),
    ):
        match = pattern.search(message)
        if match:
            value = match.group(1).strip()
            if value:
                headers[key] = value
    return headers


def build_order_modify_headers(
    records: list[dict[str, Any]],
    *,
    body_record: dict[str, Any],
    cookie: str | None = None,
    fallback_correlation_id: str | None = None,
) -> dict[str, str]:
    """Build IM headers for Order Modify (mirrors Order Create sources)."""
    header_source = find_any_v2_header_record(records)
    headers: dict[str, str] = {}

    if header_source is not None:
        request = header_source.get("request")
        if isinstance(request, dict):
            try:
                headers = build_order_create_headers(request, cookie=None)
            except OrderCreateCurlError:
                headers = {}

    if not headers:
        for record in records:
            attributes = record.get("attributes") if "attributes" in record else None
            message = ""
            if isinstance(attributes, dict):
                message = str(attributes.get("message") or "")
            if not message and isinstance(record.get("message"), str):
                message = record["message"]
            if message:
                headers = _headers_from_im_message(message)
                if headers:
                    break
                headers = _headers_from_xml_log_message(message)
                if headers:
                    break

    if not headers:
        raise OrderModifyCurlError(
            "No OrderCreate_v2* record (or IM headers in log message) found for "
            "IM-CountryCode / IM-CustomerNumber."
        )

    # Order Modify examples use IM-CorrelationId casing.
    for key in list(headers):
        if key.lower() == "im-correlationid":
            headers["IM-CorrelationId"] = headers.pop(key)

    correlation = (
        headers.get("IM-CorrelationId")
        or _record_correlation_id(body_record)
        or _record_correlation_id(header_source)
        or (fallback_correlation_id or "").strip()
        or str(uuid.uuid4())
    )
    headers["IM-CorrelationId"] = correlation

    headers.setdefault("Accept-Language", "en-us")
    headers.setdefault("Content-Type", "application/json")

    if cookie and cookie.strip():
        headers["Cookie"] = cookie.strip()

    return headers


def format_order_modify_curl(
    *,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    username: str,
    password: str,
    redact_password: bool = False,
) -> str:
    """Format a Postman-style PUT curl for Order Modify."""
    lines: list[str] = [
        f"curl --location --request PUT {_shell_quote(url)} \\",
    ]

    cookie = headers.get("Cookie")
    header_order = [
        "Accept-Language",
        "IM-SenderID",
        "IM-CountryCode",
        "IM-CustomerNumber",
        "IM-CorrelationId",
        "Content-Type",
    ]
    emitted: set[str] = set()

    for key in header_order:
        value = headers.get(key)
        if value:
            lines.append(f"--header {_shell_quote(f'{key}: {value}')} \\")
            emitted.add(key.lower())

    for key, value in headers.items():
        if key == "Cookie" or key.lower() in emitted:
            continue
        lines.append(f"--header {_shell_quote(f'{key}: {value}')} \\")

    auth_value = _basic_auth_header(username, password, redact=redact_password)
    lines.append(f"--header {_shell_quote(f'Authorization: {auth_value}')} \\")
    if cookie:
        lines.append(f"--header {_shell_quote(f'Cookie: {cookie}')} \\")

    body_json = json.dumps(body, indent=4, ensure_ascii=False)
    lines.append(f"--data {_shell_quote(body_json)}")
    return "\n".join(lines)


def is_modify_body_record(record: dict[str, Any]) -> bool:
    if not isinstance(record.get("service"), str):
        return False
    if not record["service"].startswith(MODIFY_SERVICE_PREFIX):
        return False
    request = record.get("request")
    return isinstance(request, dict) and is_order_modify_body(request)


def find_modify_body_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [record for record in records if is_modify_body_record(record)]


def should_stop_order_modify_fetch(
    records: list[dict[str, Any]],
    index: int,
    *,
    last_page: bool,
) -> bool:
    """Return True when ``records`` contain enough data to build modify curl."""
    del last_page  # modify stop does not depend on pagination position
    body_candidates = find_modify_body_records(records)
    if len(body_candidates) <= index:
        return False
    try:
        _resolve_order_id(records, body_candidates[index])
    except OrderModifyCurlError:
        return False
    return True


def build_order_modify_curl(
    record: dict[str, Any],
    *,
    records: list[dict[str, Any]],
    username: str,
    password: str = "",
    redact_password: bool = False,
    cookie: str | None = None,
    target: str | None = None,
    order_id: str | None = None,
    fallback_correlation_id: str | None = None,
) -> OrderModifyCurl:
    request = record.get("request")
    if not isinstance(request, dict) or not is_order_modify_body(request):
        raise OrderModifyCurlError("Record is missing Order Modify RequestPayload.")

    normalized_target = normalize_order_modify_target(target)
    resolved_order_id = (order_id or "").strip() or _resolve_order_id(records, record)
    url = resolve_order_modify_url(resolved_order_id, target=normalized_target)
    headers = build_order_modify_headers(
        records,
        body_record=record,
        cookie=cookie,
        fallback_correlation_id=fallback_correlation_id,
    )
    body = request

    curl = format_order_modify_curl(
        url=url,
        headers=headers,
        body=body,
        username=username,
        password=password,
        redact_password=redact_password,
    )
    return OrderModifyCurl(
        url=url,
        headers=headers,
        body=body,
        username=username,
        curl=curl,
        order_id=resolved_order_id,
        body_service=str(record.get("service") or ""),
        body_host=str(record.get("host") or ""),
        target=normalized_target,
    )


def build_order_modify_curl_from_records(
    records: list[dict[str, Any]],
    *,
    username: str,
    password: str = "",
    redact_password: bool = False,
    index: int = 0,
    cookie: str | None = None,
    target: str | None = None,
    order_id: str | None = None,
) -> OrderModifyCurl:
    body_candidates = find_modify_body_records(records)
    if not body_candidates:
        raise OrderModifyCurlError(
            "No OrderModify_v6* record with RequestPayload body found."
        )
    if index < 0 or index >= len(body_candidates):
        raise OrderModifyCurlError(
            f"Body index {index} out of range (0..{len(body_candidates) - 1})."
        )

    fallback_correlation_id = next(
        (
            corr
            for corr in (_record_correlation_id(record) for record in records)
            if corr
        ),
        None,
    )

    return build_order_modify_curl(
        body_candidates[index],
        records=records,
        username=username,
        password=password,
        redact_password=redact_password,
        cookie=cookie,
        target=target,
        order_id=order_id,
        fallback_correlation_id=fallback_correlation_id,
    )
