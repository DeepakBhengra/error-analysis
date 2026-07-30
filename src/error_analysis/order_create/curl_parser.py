from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from error_analysis.order_create.curl_builder import OrderCreateCurlError

_HEADER_RE = re.compile(r"""--header\s+(?:'([^']*)'|"([^"]*)")""")
_LOCATION_RE = re.compile(
    r"""curl\s+--location\s+(?:'([^']*)'|"([^"]*)")""",
    re.IGNORECASE,
)
_DATA_RAW_START_RE = re.compile(r"""--data-raw\s+'""")


@dataclass(frozen=True)
class ParsedCurl:
    url: str
    headers: dict[str, str]
    body: dict[str, Any]
    authorization: str | None = None


def _strip_continuations(curl_text: str) -> str:
    # Join Postman-style line continuations: " \\\n"
    text = curl_text.replace("\r\n", "\n").strip()
    text = re.sub(r"\\\s*\n", "\n", text)
    return text


def _extract_data_raw(curl_text: str) -> str:
    match = _DATA_RAW_START_RE.search(curl_text)
    if not match:
        raise OrderCreateCurlError("Curl is missing --data-raw payload.")
    start = match.end()
    # Body is single-quoted JSON; find the closing quote that ends --data-raw.
    # The formatter emits: --data-raw '{ ... }'
    end = curl_text.rfind("'")
    if end <= start:
        raise OrderCreateCurlError("Curl --data-raw payload is not closed.")
    return curl_text[start:end]


def parse_order_create_curl(curl_text: str) -> ParsedCurl:
    """Parse a Postman-style Order Create curl into URL / headers / JSON body."""
    if not curl_text or not curl_text.strip():
        raise OrderCreateCurlError("Curl text is empty.")

    # Keep original for --data-raw extraction (multi-line JSON with quotes).
    raw = curl_text.replace("\r\n", "\n")
    flat = _strip_continuations(raw)

    loc = _LOCATION_RE.search(flat)
    if not loc:
        raise OrderCreateCurlError("Curl is missing curl --location '<url>'.")
    url = (loc.group(1) or loc.group(2) or "").strip()
    if not url:
        raise OrderCreateCurlError("Curl --location URL is empty.")

    headers: dict[str, str] = {}
    authorization: str | None = None
    for match in _HEADER_RE.finditer(flat):
        value = match.group(1) if match.group(1) is not None else match.group(2)
        if not value or ":" not in value:
            continue
        key, val = value.split(":", 1)
        key = key.strip()
        val = val.strip()
        if key.lower() == "authorization":
            authorization = val
            continue
        headers[key] = val

    data_raw = _extract_data_raw(raw)
    try:
        body = json.loads(data_raw)
    except json.JSONDecodeError as exc:
        raise OrderCreateCurlError(f"Curl --data-raw is not valid JSON: {exc}") from exc
    if not isinstance(body, dict):
        raise OrderCreateCurlError("Curl --data-raw must be a JSON object.")

    return ParsedCurl(
        url=url,
        headers=headers,
        body=body,
        authorization=authorization,
    )
