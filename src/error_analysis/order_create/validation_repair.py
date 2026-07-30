"""Repair Order Create curls from immediate HTTP validation responses.

Only deterministic / protocol fields are auto-filled. Business fields that
cannot be inferred safely are reported as unresolved for manual editing.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from error_analysis.order_create.curl_builder import format_order_create_curl
from error_analysis.order_create.curl_parser import parse_order_create_curl

# Canonical header name -> generator of a safe default value.
_DETERMINISTIC_HEADERS: dict[str, Callable[[], str]] = {
    "im-correlationid": lambda: str(uuid.uuid4()),
    "content-type": lambda: "application/json",
}

_CANONICAL_HEADER_NAMES: dict[str, str] = {
    "im-correlationid": "IM-CorrelationId",
    "content-type": "Content-Type",
}


@dataclass(frozen=True)
class ValidationFieldError:
    field: str
    value: str
    message: str


@dataclass
class CurlRepairResult:
    repaired: bool
    curl: str
    repaired_fields: list[str] = field(default_factory=list)
    unresolved_fields: list[str] = field(default_factory=list)
    message: str = ""


def extract_validation_fields(http_body: Any) -> list[ValidationFieldError]:
    """Extract ``errors[].fields[]`` entries from an Order Create API response."""
    if not isinstance(http_body, dict):
        return []
    errors = http_body.get("errors")
    if not isinstance(errors, list):
        return []

    found: list[ValidationFieldError] = []
    for error in errors:
        if not isinstance(error, dict):
            continue
        fields = error.get("fields")
        if not isinstance(fields, list):
            continue
        for item in fields:
            if not isinstance(item, dict):
                continue
            name = item.get("field")
            if not isinstance(name, str) or not name.strip():
                continue
            value = item.get("value")
            message = item.get("message")
            found.append(
                ValidationFieldError(
                    field=name.strip(),
                    value=value if isinstance(value, str) else "",
                    message=message if isinstance(message, str) else "",
                )
            )
    return found


def _header_lookup(headers: dict[str, str], field_name: str) -> str | None:
    target = field_name.strip().lower()
    for key in headers:
        if key.lower() == target:
            return key
    return None


def _is_blank(value: str | None) -> bool:
    return value is None or not str(value).strip()


def repair_order_create_curl(
    curl_text: str,
    http_body: Any,
    *,
    username: str,
    password: str,
    authorization: str | None = None,
) -> CurlRepairResult:
    """Regenerate curl with deterministic missing headers filled in.

    Does not POST. Unknown / business body fields are left unresolved.
    """
    fields = extract_validation_fields(http_body)
    if not fields:
        return CurlRepairResult(
            repaired=False,
            curl=curl_text,
            message="",
        )

    parsed = parse_order_create_curl(curl_text)
    headers = dict(parsed.headers)
    repaired_fields: list[str] = []
    unresolved_fields: list[str] = []

    for item in fields:
        key_lower = item.field.strip().lower()
        generator = _DETERMINISTIC_HEADERS.get(key_lower)
        if generator is None:
            unresolved_fields.append(item.field)
            continue

        existing_key = _header_lookup(headers, item.field)
        existing_value = headers.get(existing_key) if existing_key else None
        # Only fill when missing or blank (including empty string from API).
        if existing_key and not _is_blank(existing_value):
            continue

        canonical = _CANONICAL_HEADER_NAMES.get(key_lower, item.field)
        if existing_key and existing_key != canonical:
            del headers[existing_key]
        headers[canonical] = generator()
        repaired_fields.append(canonical)

    if not repaired_fields:
        message = ""
        if unresolved_fields:
            message = (
                "Validation reported missing fields that cannot be safely inferred: "
                + ", ".join(unresolved_fields)
            )
        return CurlRepairResult(
            repaired=False,
            curl=curl_text,
            repaired_fields=[],
            unresolved_fields=unresolved_fields,
            message=message,
        )

    # Prefer .env credentials; fall back to curl Authorization like replay does.
    if username.strip() and password:
        rebuilt = format_order_create_curl(
            url=parsed.url,
            headers=headers,
            body=parsed.body,
            username=username,
            password=password,
            redact_password=False,
        )
    else:
        rebuilt = format_order_create_curl(
            url=parsed.url,
            headers=headers,
            body=parsed.body,
            username="user",
            password="",
            redact_password=True,
        )
        if authorization:
            # Replace redacted Authorization with the original token.
            rebuilt = rebuilt.replace(
                "--header 'Authorization: Basic ***'",
                f"--header 'Authorization: {authorization}'",
            )

    parts = [f"Repaired curl: added {', '.join(repaired_fields)}."]
    if unresolved_fields:
        parts.append(
            "Still unresolved (edit manually): " + ", ".join(unresolved_fields) + "."
        )
    parts.append("Review the curl and click Re-Submit.")

    return CurlRepairResult(
        repaired=True,
        curl=rebuilt,
        repaired_fields=repaired_fields,
        unresolved_fields=unresolved_fields,
        message=" ".join(parts),
    )
