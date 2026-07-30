from __future__ import annotations

import re
from typing import Any

import httpx

from error_analysis.config import Settings

_TWO_CHAR_CODE = re.compile(r"^[A-Za-z][A-Za-z0-9]$")


class ErrorLookupError(Exception):
    pass


def is_two_char_error_code(code: str) -> bool:
    """True for CORORA-style two-char codes (e.g. EN, SE, D9).

    Codes start with a letter followed by a letter or digit, so numeric HTTP
    statuses like 400 never qualify.
    """
    return bool(_TWO_CHAR_CODE.match((code or "").strip()))


def _paths_body(settings: Settings) -> dict[str, str]:
    return {
        "source_root": settings.lookup_source_root,
        "rules_path": settings.lookup_rules_path,
        "corora_mappings": settings.lookup_corora_mappings,
    }


def _build_request_body(settings: Settings, error_code: str) -> dict[str, str]:
    return {
        "error_code": error_code.strip().upper(),
        **_paths_body(settings),
    }


def _build_field_request_body(settings: Settings, error_field: str) -> dict[str, str]:
    return {
        "error_field": error_field.strip(),
        **_paths_body(settings),
    }


def _first_finding_with_error_code(findings: list[Any]) -> dict[str, Any]:
    for item in findings:
        if not isinstance(item, dict):
            continue
        code = item.get("error_code")
        if isinstance(code, str) and code.strip():
            return item
    return findings[0] if findings and isinstance(findings[0], dict) else {}


def _normalize_response(payload: dict[str, Any]) -> dict[str, Any]:
    findings = payload.get("findings") or []
    if not isinstance(findings, list):
        findings = []
    first = _first_finding_with_error_code(findings)
    query = payload.get("query") or {}

    return {
        "error_code": (first.get("error_code") or query.get("error_code") or ""),
        "error_field": first.get("error_field") or query.get("error_field") or "",
        "historical_resolution": first.get("historical_resolution") or "",
        "program": first.get("program") or "",
        "paragraph": first.get("paragraph") or "",
        "line": first.get("line"),
        "summary": first.get("summary") or "",
        "program_count": payload.get("program_count", 0),
        "finding_count": payload.get("finding_count", 0),
        "findings": findings,
        "query": query,
    }


def _post_lookup(settings: Settings, body: dict[str, str]) -> dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "X-API-Key": settings.lookup_api_key,
        "X-Application-Key": settings.lookup_application_key,
    }

    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(settings.lookup_api_url, json=body, headers=headers)
    except httpx.RequestError as exc:
        raise ErrorLookupError(f"Lookup service unreachable: {exc}") from exc

    if response.status_code >= 400:
        detail = response.text.strip() or response.reason_phrase
        raise ErrorLookupError(
            f"Lookup service returned {response.status_code}: {detail}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise ErrorLookupError("Lookup service returned invalid JSON") from exc

    if not isinstance(payload, dict):
        raise ErrorLookupError("Lookup service returned an unexpected response")

    return _normalize_response(payload)


def lookup_error_code(settings: Settings, error_code: str) -> dict[str, Any]:
    code = error_code.strip().upper()
    if not code:
        raise ErrorLookupError("error_code is required")

    normalized = _post_lookup(settings, _build_request_body(settings, code))
    if normalized["finding_count"] == 0 and not normalized["findings"]:
        raise ErrorLookupError(f"No findings returned for error code {code!r}")

    return normalized


def lookup_error_field(settings: Settings, error_field: str) -> dict[str, Any]:
    field = error_field.strip()
    if not field:
        raise ErrorLookupError("error_field is required")

    normalized = _post_lookup(settings, _build_field_request_body(settings, field))
    mapped = str(normalized.get("error_code") or "").strip()
    if not mapped:
        raise ErrorLookupError(f"No error_code found for error_field {field!r}")
    if normalized["finding_count"] == 0 and not normalized["findings"]:
        raise ErrorLookupError(f"No findings returned for error_field {field!r}")

    normalized["error_code"] = mapped.upper() if is_two_char_error_code(mapped) else mapped
    return normalized
