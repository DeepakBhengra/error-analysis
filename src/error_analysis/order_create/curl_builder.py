from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any

from error_analysis.order_create.v2_to_v6 import (
    OrderCreateV2ToV6Error,
    convert_v2_to_v6,
)

UAT_ORDERS_URL = (
    "https://imservices-uat-usch01.corporate.ingrammicro.com:9043/resellers/v6/orders"
)
QA_ORDERS_URL = (
    "https://imservices-qa-usch01.corporate.ingrammicro.com:9043/resellers/v6/orders"
)

V6_BODY_SERVICE = "OrderCreate_v6"
V6_BODY_HOST = "uschileai2503"
V2_HEADER_SERVICE = "OrderCreate_v2"
V2_HEADER_HOST = "uschileai2501"

ASYNC_BODY_SERVICE = "AsyncOrderCreate"
# Prod Order Create hosts. AsyncOrderCreate as well as the synchronous prod
# services (OrderCreate_v6_*, OrderCreate_v2_*) all run on these hosts.
PROD_ORDER_HOSTS: frozenset[str] = frozenset(
    {
        "uschileai1401",
        "uschileai1402",
        "uschileai1403",
        "uschileai1404",
    }
)
# Backward-compatible alias (async feature originally used this name).
ASYNC_BODY_HOSTS: frozenset[str] = PROD_ORDER_HOSTS

# Prod service families are versioned, e.g. OrderCreate_v6_1 / OrderCreate_v2_0.
V6_SERVICE_PREFIX = "OrderCreate_v6"
V2_SERVICE_PREFIX = "OrderCreate_v2"


def _is_prod_v6_body_service(service: Any) -> bool:
    return isinstance(service, str) and (
        service == ASYNC_BODY_SERVICE or service.startswith(V6_SERVICE_PREFIX)
    )


def _is_v2_family_service(service: Any) -> bool:
    return isinstance(service, str) and service.startswith(V2_SERVICE_PREFIX)

TARGET_URLS: dict[str, str] = {
    "uat": UAT_ORDERS_URL,
    "qa": QA_ORDERS_URL,
}

# (service, host) → Order Create URL
SERVICE_HOST_URL_MAP: dict[tuple[str, str], str] = {
    ("OrderCreate_v2", "uschileai2501"): UAT_ORDERS_URL,
    ("OrderCreate_v2", "uschleai2403"): QA_ORDERS_URL,
    ("OrderCreate_v6", "uschileai2503"): UAT_ORDERS_URL,
}

# Backward-compatible alias used by older tests/imports
HOST_URL_MAP: dict[str, str] = {
    host: url for (_service, host), url in SERVICE_HOST_URL_MAP.items()
}


class OrderCreateCurlError(ValueError):
    """Raised when a Datadog record cannot be turned into an Order Create curl."""


@dataclass(frozen=True)
class OrderCreateCurl:
    url: str
    headers: dict[str, str]
    body: dict[str, Any]
    username: str
    curl: str
    body_service: str = ""
    body_host: str = ""
    header_service: str = ""
    header_host: str = ""
    # "v6" when the Datadog body was already portal v6; "v2-converted" when
    # convert_v2_to_v6() produced the body from an OrderCreate_v2 payload.
    source: str = "v6"


def resolve_order_create_url(
    service: str | None,
    host: str | None,
    *,
    target: str | None = None,
) -> str:
    """Resolve the Order Create URL.

    When ``target`` is ``uat``/``qa`` and the record is an AsyncOrderCreate
    body, use that endpoint. Otherwise fall back to SERVICE_HOST_URL_MAP.
    """
    normalized_target = (target or "").strip().lower()
    if (
        (_is_prod_v6_body_service(service) or _is_v2_family_service(service))
        and (host or "") in PROD_ORDER_HOSTS
        and normalized_target
    ):
        if normalized_target not in TARGET_URLS:
            raise OrderCreateCurlError(
                f"Unsupported target {target!r}. Expected one of: "
                f"{', '.join(sorted(TARGET_URLS))}."
            )
        return TARGET_URLS[normalized_target]

    key = (service or "", host or "")
    if key in SERVICE_HOST_URL_MAP:
        return SERVICE_HOST_URL_MAP[key]

    # Test / non-portal OrderCreate_v2* hosts (e.g. uschleai3501) replay via UAT/QA.
    if _is_v2_family_service(service) and normalized_target in TARGET_URLS:
        return TARGET_URLS[normalized_target]

    known = ", ".join(
        f"{svc}/{hst}" for svc, hst in sorted(SERVICE_HOST_URL_MAP)
    )
    raise OrderCreateCurlError(
        f"Unsupported service/host {service!r}/{host!r}. "
        f"Known pairs: {known}."
    )


def normalize_order_create_target(target: str | None) -> str:
    """Normalize and validate a UAT/QA target selector."""
    normalized = (target or "uat").strip().lower() or "uat"
    if normalized not in TARGET_URLS:
        raise OrderCreateCurlError(
            f"Unsupported target {target!r}. Expected one of: "
            f"{', '.join(sorted(TARGET_URLS))}."
        )
    return normalized


def _preamble_from_request(request: Any) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise OrderCreateCurlError("Record request must be a JSON object.")
    order_create = request.get("ordercreaterequest")
    if not isinstance(order_create, dict):
        raise OrderCreateCurlError(
            "Record request is missing ordercreaterequest object."
        )
    preamble = order_create.get("requestpreamble")
    if not isinstance(preamble, dict):
        raise OrderCreateCurlError(
            "ordercreaterequest is missing requestpreamble object."
        )
    return preamble


def _extended_spec_value(request: dict[str, Any], attribute_name: str) -> str | None:
    order_create = request.get("ordercreaterequest")
    if not isinstance(order_create, dict):
        return None
    details = order_create.get("ordercreatedetails")
    if not isinstance(details, dict):
        return None
    specs = details.get("extendedspecs")
    if not isinstance(specs, list):
        return None
    target = attribute_name.upper()
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        name = spec.get("attributename")
        if isinstance(name, str) and name.upper() == target:
            value = spec.get("attributevalue")
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def build_order_create_headers(
    request: Any,
    *,
    cookie: str | None = None,
) -> dict[str, str]:
    """Build IM headers from OrderCreate_v2 requestpreamble + extendedspecs."""
    preamble = _preamble_from_request(request)
    country = preamble.get("isocountrycode")
    customer = preamble.get("customernumber")
    if not isinstance(country, str) or not country.strip():
        raise OrderCreateCurlError(
            "requestpreamble.isocountrycode is required for IM-CountryCode."
        )
    if not isinstance(customer, str) or not customer.strip():
        raise OrderCreateCurlError(
            "requestpreamble.customernumber is required for IM-CustomerNumber."
        )

    headers: dict[str, str] = {
        "IM-CountryCode": country.strip(),
        "IM-CustomerNumber": customer.strip(),
    }

    correlation = _extended_spec_value(request, "IM-CORRELATIONID")
    sender = _extended_spec_value(request, "IM-SENDERID")
    if correlation:
        headers["IM-CorrelationID"] = correlation
    if sender:
        headers["IM-SenderID"] = sender

    headers["Content-Type"] = "application/json"
    if cookie and cookie.strip():
        headers["Cookie"] = cookie.strip()
    return headers


def build_order_create_headers_from_async_metadata(
    request: Any,
    *,
    cookie: str | None = None,
) -> dict[str, str]:
    """Build IM headers from AsyncOrderCreate metadata (countryCode/customerNumber)."""
    if not isinstance(request, dict):
        raise OrderCreateCurlError("AsyncOrderCreate header record must be a JSON object.")
    country = request.get("countryCode")
    customer = request.get("customerNumber")
    if not isinstance(country, str) or not country.strip():
        raise OrderCreateCurlError(
            "AsyncOrderCreate metadata countryCode is required for IM-CountryCode."
        )
    if not isinstance(customer, str) or not customer.strip():
        raise OrderCreateCurlError(
            "AsyncOrderCreate metadata customerNumber is required for IM-CustomerNumber."
        )

    headers: dict[str, str] = {
        "IM-CountryCode": country.strip(),
        "IM-CustomerNumber": customer.strip(),
    }
    correlation = request.get("correlationId")
    sender = request.get("senderId")
    if isinstance(correlation, str) and correlation.strip():
        headers["IM-CorrelationID"] = correlation.strip()
    if isinstance(sender, str) and sender.strip():
        headers["IM-SenderID"] = sender.strip()

    headers["Content-Type"] = "application/json"
    if cookie and cookie.strip():
        headers["Cookie"] = cookie.strip()
    return headers


def _headers_from_source(
    header_source: dict[str, Any],
    *,
    cookie: str | None = None,
) -> tuple[dict[str, str], str, str]:
    """Return (headers, header_service, header_host) from a sibling header record."""
    header_request = header_source.get("request")
    if not isinstance(header_request, dict):
        raise OrderCreateCurlError(
            "Header source record is missing request object."
        )
    header_service = str(header_source.get("service") or "")
    header_host = str(header_source.get("host") or "")
    # Detect by payload shape so versioned prod services work regardless of name:
    # OrderCreate_v2* carry ordercreaterequest/requestpreamble; v6-family and
    # AsyncOrderCreate metadata carry countryCode/customerNumber.
    if isinstance(header_request.get("ordercreaterequest"), dict):
        headers = build_order_create_headers(header_request, cookie=cookie)
    else:
        try:
            headers = build_order_create_headers_from_async_metadata(
                header_request, cookie=cookie
            )
        except OrderCreateCurlError:
            headers = build_order_create_headers(header_request, cookie=cookie)
    return headers, header_service, header_host


def _shell_quote(value: str) -> str:
    """Postman-style single quotes (always), escaping any embedded quotes."""
    return "'" + value.replace("'", "'\\''") + "'"


def _basic_auth_header(username: str, password: str, *, redact: bool) -> str:
    if redact:
        return "Basic ***"
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def format_order_create_curl(
    *,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    username: str,
    password: str,
    redact_password: bool = False,
) -> str:
    """Format a Postman-style curl ( --location / --header / --data-raw )."""
    lines: list[str] = [
        f"curl --location {_shell_quote(url)} \\",
    ]

    # IM / Content-Type headers first (Cookie emitted after Authorization).
    cookie = headers.get("Cookie")
    for key, value in headers.items():
        if key == "Cookie":
            continue
        lines.append(f"--header {_shell_quote(f'{key}: {value}')} \\")

    auth_value = _basic_auth_header(username, password, redact=redact_password)
    lines.append(f"--header {_shell_quote(f'Authorization: {auth_value}')} \\")
    if cookie:
        lines.append(f"--header {_shell_quote(f'Cookie: {cookie}')} \\")

    body_json = json.dumps(body, indent=4, ensure_ascii=False)
    data_lines = body_json.splitlines()
    if not data_lines:
        lines.append("--data-raw '{}'")
        return "\n".join(lines)

    lines.append(f"--data-raw '{data_lines[0]}")
    for mid in data_lines[1:-1]:
        lines.append(mid)
    if len(data_lines) == 1:
        lines[-1] = f"--data-raw '{data_lines[0]}'"
    else:
        lines.append(f"{data_lines[-1]}'")
    return "\n".join(lines)


def is_portal_order_body(request: dict[str, Any]) -> bool:
    """True for reseller v6 portal Order Create request payloads."""
    return (
        "customerOrderNumber" in request
        and isinstance(request.get("lines"), list)
        and "resellerInfo" in request
    )


def is_v6_body_record(record: dict[str, Any]) -> bool:
    return (
        record.get("service") == V6_BODY_SERVICE
        and record.get("host") == V6_BODY_HOST
        and isinstance(record.get("request"), dict)
    )


def is_prod_v6_body_record(record: dict[str, Any]) -> bool:
    """True for prod v6 portal bodies on uschileai1401-1404.

    Covers AsyncOrderCreate as well as the synchronous prod services
    (OrderCreate_v6, OrderCreate_v6_1, ...).
    """
    request = record.get("request")
    return (
        _is_prod_v6_body_service(record.get("service"))
        and record.get("host") in PROD_ORDER_HOSTS
        and isinstance(request, dict)
        and is_portal_order_body(request)
    )


def is_async_v6_body_record(record: dict[str, Any]) -> bool:
    """True for prod AsyncOrderCreate records on uschileai1401-1404 with a v6 body."""
    request = record.get("request")
    return (
        record.get("service") == ASYNC_BODY_SERVICE
        and record.get("host") in PROD_ORDER_HOSTS
        and isinstance(request, dict)
        and is_portal_order_body(request)
    )


def is_v2_header_record(record: dict[str, Any]) -> bool:
    if (
        record.get("service") != V2_HEADER_SERVICE
        or record.get("host") != V2_HEADER_HOST
    ):
        return False
    request = record.get("request")
    if not isinstance(request, dict):
        return False
    try:
        build_order_create_headers(request)
    except OrderCreateCurlError:
        return False
    return True


def is_any_v2_header_record(record: dict[str, Any]) -> bool:
    """Accept any OrderCreate_v2* record with a usable requestpreamble (any host)."""
    if not _is_v2_family_service(record.get("service")):
        return False
    request = record.get("request")
    if not isinstance(request, dict):
        return False
    try:
        build_order_create_headers(request)
    except OrderCreateCurlError:
        return False
    return True


def is_async_header_record(record: dict[str, Any]) -> bool:
    """v6-family / AsyncOrderCreate metadata (countryCode + customerNumber)."""
    if not _is_prod_v6_body_service(record.get("service")):
        return False
    if is_prod_v6_body_record(record):
        return False
    request = record.get("request")
    if not isinstance(request, dict):
        return False
    try:
        build_order_create_headers_from_async_metadata(request)
    except OrderCreateCurlError:
        return False
    return True


def is_mapped_v2_body_record(record: dict[str, Any]) -> bool:
    service = record.get("service")
    host = record.get("host")
    request = record.get("request")
    return (
        isinstance(service, str)
        and isinstance(host, str)
        and service == "OrderCreate_v2"
        and (service, host) in SERVICE_HOST_URL_MAP
        and isinstance(request, dict)
    )


def is_prod_v2_body_record(record: dict[str, Any]) -> bool:
    """True for prod OrderCreate_v2* records on uschileai1401-1404 with a
    convertible ordercreaterequest payload (e.g. OrderCreate_v2_0)."""
    request = record.get("request")
    return (
        _is_v2_family_service(record.get("service"))
        and record.get("host") in PROD_ORDER_HOSTS
        and isinstance(request, dict)
        and isinstance(request.get("ordercreaterequest"), dict)
    )


def is_convertible_v2_body_record(record: dict[str, Any]) -> bool:
    """Any OrderCreate_v2* record with an ordercreaterequest payload (any host)."""
    request = record.get("request")
    return (
        _is_v2_family_service(record.get("service"))
        and isinstance(request, dict)
        and isinstance(request.get("ordercreaterequest"), dict)
    )


def _is_buildable_body_request(request: Any) -> bool:
    """True when build_order_create_curl can produce a v6 body from this request."""
    if not isinstance(request, dict):
        return False
    if is_portal_order_body(request):
        return True
    return (
        isinstance(request.get("ordercreaterequest"), dict)
        or "customerponumber" in request
        or "ordercreatedetails" in request
    )


def find_prod_v6_body_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [record for record in records if is_prod_v6_body_record(record)]


def find_async_v6_body_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [record for record in records if is_async_v6_body_record(record)]


def find_v6_body_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Metadata-only v6 records (e.g. {"apiEndpoint": ...}) are excluded so
    # selection can fall through to a convertible OrderCreate_v2* record.
    v6 = [
        record
        for record in records
        if is_v6_body_record(record) and _is_buildable_body_request(record["request"])
    ]
    portal = [
        record
        for record in v6
        if is_portal_order_body(record["request"])  # type: ignore[arg-type]
    ]
    return portal or v6


def find_v2_header_record(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    for record in records:
        if is_v2_header_record(record):
            return record
    return None


def find_any_v2_header_record(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    for record in records:
        if is_any_v2_header_record(record):
            return record
    return None


def find_async_header_record(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    for record in records:
        if is_async_header_record(record):
            return record
    return None


def find_order_create_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Body candidates: prefer prod v6 (Async/OrderCreate_v6_* on uschileai1401-04),
    then portal OrderCreate_v6/uschileai2503, then mapped v2, else prod
    OrderCreate_v2* (v2-to-v6 conversion)."""
    prod_bodies = find_prod_v6_body_records(records)
    if prod_bodies:
        return prod_bodies
    v6 = find_v6_body_records(records)
    if v6:
        return v6
    mapped_v2 = [
        record
        for record in records
        if is_mapped_v2_body_record(record)
        and _is_buildable_body_request(record.get("request"))
    ]
    if mapped_v2:
        return mapped_v2
    return [record for record in records if is_convertible_v2_body_record(record)]


def should_stop_order_create_fetch(
    records: list[dict[str, Any]],
    index: int,
    *,
    last_page: bool,
) -> bool:
    """Return True when ``records`` are enough to build curl at ``index``.

    Portal v6 bodies may be superseded by prod v6 on a later page, so stop only
    on the last page unless a higher-priority prod or v2 body is already present.
    """
    body_candidates = find_order_create_records(records)
    if len(body_candidates) <= index:
        return False

    body_record = body_candidates[index]
    if is_prod_v6_body_record(body_record):
        return (
            find_any_v2_header_record(records) is not None
            or find_async_header_record(records) is not None
        )
    if is_v6_body_record(body_record):
        if find_v2_header_record(records) is None:
            return False
        return last_page
    if is_mapped_v2_body_record(body_record) or is_convertible_v2_body_record(
        body_record
    ):
        return True
    return False


def _record_correlation_id(record: dict[str, Any] | None) -> str | None:
    """CorrelationId captured from the log XML wrapper (e.g. <pfx5:CorrelationId>)."""
    if not isinstance(record, dict):
        return None
    value = record.get("correlation_id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _has_correlation_header(headers: dict[str, str]) -> bool:
    return any(key.lower() == "im-correlationid" for key in headers)


def build_order_create_curl(
    record: dict[str, Any],
    *,
    username: str,
    password: str = "",
    redact_password: bool = False,
    header_source: dict[str, Any] | None = None,
    cookie: str | None = None,
    target: str | None = None,
    fallback_correlation_id: str | None = None,
) -> OrderCreateCurl:
    service = record.get("service")
    host = record.get("host")
    request = record.get("request")
    if not isinstance(request, dict):
        raise OrderCreateCurlError("Record is missing request object.")

    normalized_target = normalize_order_create_target(target)
    if (
        is_prod_v6_body_record(record)
        or is_prod_v2_body_record(record)
        or is_convertible_v2_body_record(record)
    ):
        url = resolve_order_create_url(
            service if isinstance(service, str) else None,
            host if isinstance(host, str) else None,
            target=normalized_target,
        )
    else:
        url = resolve_order_create_url(
            service if isinstance(service, str) else None,
            host if isinstance(host, str) else None,
        )

    if header_source is not None:
        headers, header_service, header_host = _headers_from_source(
            header_source, cookie=cookie
        )
    elif is_prod_v6_body_record(record) or is_v6_body_record(record):
        raise OrderCreateCurlError(
            "v6 / AsyncOrderCreate body requires a sibling OrderCreate_v2 "
            "(or v6/AsyncOrderCreate metadata) record for IM-CountryCode / "
            "IM-CustomerNumber."
        )
    else:
        headers = build_order_create_headers(request, cookie=cookie)
        header_service = str(service or "")
        header_host = str(host or "")

    if not _has_correlation_header(headers):
        correlation = (
            _record_correlation_id(header_source)
            or _record_correlation_id(record)
            or (fallback_correlation_id or "").strip()
        )
        if correlation:
            headers["IM-CorrelationID"] = correlation

    source = "v6"
    body: dict[str, Any]
    if is_portal_order_body(request):
        body = request
    elif isinstance(request.get("ordercreaterequest"), dict) or (
        "customerponumber" in request or "ordercreatedetails" in request
    ):
        try:
            body = convert_v2_to_v6(request)
        except OrderCreateV2ToV6Error as exc:
            raise OrderCreateCurlError(
                f"Failed to convert OrderCreate_v2 body to v6: {exc}"
            ) from exc
        source = "v2-converted"
    else:
        raise OrderCreateCurlError(
            "Record request is neither a portal Order Create v6 body "
            "nor a convertible OrderCreate_v2 payload."
        )

    curl = format_order_create_curl(
        url=url,
        headers=headers,
        body=body,
        username=username,
        password=password,
        redact_password=redact_password,
    )
    return OrderCreateCurl(
        url=url,
        headers=headers,
        body=body,
        username=username,
        curl=curl,
        body_service=str(service or ""),
        body_host=str(host or ""),
        header_service=header_service,
        header_host=header_host,
        source=source,
    )


def build_order_create_curl_from_records(
    records: list[dict[str, Any]],
    *,
    username: str,
    password: str = "",
    redact_password: bool = False,
    index: int = 0,
    cookie: str | None = None,
    target: str | None = None,
) -> OrderCreateCurl:
    """
    Build Postman-style curl from Datadog results:
    - Body/URL from prod v6 (AsyncOrderCreate / OrderCreate_v6_* on
      uschileai1401-04) when present
    - Else portal OrderCreate_v6/uschileai2503 when present
    - IM-CountryCode / IM-CustomerNumber / Correlation / Sender from
      OrderCreate_v2* (preferred) or v6/AsyncOrderCreate metadata (fallback)
    """
    normalized_target = normalize_order_create_target(target)
    body_candidates = find_order_create_records(records)
    if not body_candidates:
        raise OrderCreateCurlError(
            "No Order Create body record found (AsyncOrderCreate / "
            "OrderCreate_v6_* on uschileai1401-04, OrderCreate_v6/uschileai2503, "
            "mapped OrderCreate_v2, or OrderCreate_v2* with ordercreaterequest)."
        )
    if index < 0 or index >= len(body_candidates):
        raise OrderCreateCurlError(
            f"Body index {index} out of range (0..{len(body_candidates) - 1})."
        )

    body_record = body_candidates[index]
    header_source: dict[str, Any] | None = None
    if is_prod_v6_body_record(body_record):
        header_source = find_any_v2_header_record(records)
        if header_source is None:
            header_source = find_async_header_record(records)
        if header_source is None:
            raise OrderCreateCurlError(
                "Found prod v6 body but no OrderCreate_v2* (or v6/AsyncOrderCreate "
                "metadata with countryCode/customerNumber) record for headers."
            )
    elif is_v6_body_record(body_record):
        header_source = find_v2_header_record(records)
        if header_source is None:
            raise OrderCreateCurlError(
                "Found OrderCreate_v6/uschileai2503 body but no OrderCreate_v2/"
                f"{V2_HEADER_HOST} with isocountrycode/customernumber for headers."
            )

    # CorrelationId from any sibling log record (captured from the XML wrapper,
    # e.g. <pfx5:CorrelationId>bw0a10kkdu-...>) as a last-resort header source.
    fallback_correlation_id = next(
        (
            corr
            for corr in (_record_correlation_id(record) for record in records)
            if corr
        ),
        None,
    )

    return build_order_create_curl(
        body_record,
        username=username,
        password=password,
        redact_password=redact_password,
        header_source=header_source,
        cookie=cookie,
        target=normalized_target,
        fallback_correlation_id=fallback_correlation_id,
    )
