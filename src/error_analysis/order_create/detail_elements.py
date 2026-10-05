"""Parse ORRORD-DETAIL-ELEMENTS into ORRORC comment and ORRORL line records."""

from __future__ import annotations

import html
import re
from typing import Any

from error_analysis.order_create.copybook_layout import (
    load_pic_copybook,
    map_fixed_width_record,
    numbered_report_lines,
)

DETAIL_RECORD_LENGTH = 1980
COMMENT_KINDS = frozenset({"CL", "EC"})
LINE_KIND = "OL"
# Record kinds at column 0 or after whitespace. Do not use a raw
# ``find("CL")`` — that matches the letters inside words such as INCL.
_RECORD_START_RE = re.compile(r"(?:(?<=^)|(?<=[\t\n\r ]))(?:CL|OL)")

_DETAIL_OPEN_RE = re.compile(
    r"<(?:\w+:)?ORRORD-DETAIL-ELEMENTS\b[^>]*>",
    re.IGNORECASE,
)
_DETAIL_CLOSE_RE = re.compile(
    r"</(?:\w+:)?ORRORD-DETAIL-ELEMENTS>",
    re.IGNORECASE,
)


def first_detail_record_start(detail_text: str) -> int:
    """Index of the first ``CL`` or ``OL`` record, whichever appears first."""
    match = _RECORD_START_RE.search(detail_text or "")
    return match.start() if match else -1


def extract_detail_elements(xml_text: str) -> str:
    """Return the raw ORRORD-DETAIL-ELEMENTS payload, unescaped."""
    if not xml_text or not isinstance(xml_text, str):
        return ""
    text = html.unescape(xml_text)
    start = _DETAIL_OPEN_RE.search(text)
    if not start:
        return ""
    end = _DETAIL_CLOSE_RE.search(text, start.end())
    inner = text[start.end() : end.start()] if end else text[start.end() :]
    return inner


def split_detail_records(detail_text: str) -> list[tuple[str, str]]:
    """Slice from the first ``CL`` or ``OL`` in 1980-byte records.

    Some Substation payloads have no comment header and start at ``OL``.
    """
    text = detail_text or ""
    start = first_detail_record_start(text)
    if start < 0:
        return []
    records: list[tuple[str, str]] = []
    pos = start
    while pos < len(text):
        chunk = text[pos : pos + DETAIL_RECORD_LENGTH]
        if len(chunk) < 2:
            break
        if len(chunk) < DETAIL_RECORD_LENGTH:
            chunk = chunk.ljust(DETAIL_RECORD_LENGTH)
        kind = chunk[:2]
        if kind.strip():
            records.append((kind, chunk))
        pos += DETAIL_RECORD_LENGTH
    return records


def _record_payload(kind: str, fields: list[dict[str, Any]]) -> dict[str, Any]:
    lines = numbered_report_lines(fields)
    return {
        "kind": kind,
        "report": "\n".join(lines),
        "fields": fields,
    }


def parse_detail_element_records(detail_text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (comment/ORRORC records, line/ORRORL records)."""
    comment_model = load_pic_copybook("ORRORC", "ORRORC-REQUEST-FUNCTION")
    line_model = load_pic_copybook("ORRORL", "ORRORL-REQUEST-FUNCTION")
    comments: list[dict[str, Any]] = []
    lines: list[dict[str, Any]] = []
    for kind, chunk in split_detail_records(detail_text):
        if kind in COMMENT_KINDS:
            comments.append(
                _record_payload(kind, map_fixed_width_record(chunk, comment_model))
            )
        elif kind == LINE_KIND:
            lines.append(
                _record_payload(kind, map_fixed_width_record(chunk, line_model))
            )
    return comments, lines


def parse_detail_elements_from_xml(
    xml_text: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return parse_detail_element_records(extract_detail_elements(xml_text))
