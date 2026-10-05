"""Generic COBOL PIC layout + 88-level parsing for ORROR* copybooks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from error_analysis.order_create.orrorh_report import (
    FILLER_TOKEN,
    OrrorhCondition,
    SPACES_VALUE,
    _cobol_literals,
    _copybook_body,
    _is_comment_line,
    condition_matches,
)

_PIC_LINE_RE = re.compile(
    r"^\s*(?:\d{6})?\s*(\d{2})\s+([A-Z0-9][A-Z0-9-]*)\s+PIC\s+(\S+)",
    re.IGNORECASE,
)
_LEVEL88_RE = re.compile(
    r"^\s*88\s+([A-Z0-9][A-Z0-9-]*)\b",
    re.IGNORECASE,
)
_PIC_TOKEN_RE = re.compile(r"([X9])(?:\((\d+)\))?", re.IGNORECASE)


def copybooks_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "copybooks"


def pic_storage_length(clause: str) -> int:
    """Bytes stored for a PIC clause (implied-decimal V does not add a byte)."""
    cleaned = re.sub(r"\s+", "", (clause or "").split(".")[0].upper())
    if cleaned.startswith("S"):
        cleaned = cleaned[1:]
    if not cleaned:
        raise ValueError(f"Empty PIC clause: {clause!r}")
    total = 0
    for part in cleaned.split("V"):
        match = _PIC_TOKEN_RE.fullmatch(part)
        if not match:
            raise ValueError(f"Unsupported PIC clause: {clause!r}")
        total += int(match.group(2) or 1)
    return total


@dataclass(frozen=True)
class LayoutField:
    name: str
    length: int
    conditions: tuple[OrrorhCondition, ...] = ()
    skip: bool = False


def parse_pic_copybook(
    copybook_text: str,
    *,
    start_field: str,
) -> list[LayoutField]:
    """Elementary PIC fields from ``start_field``, with 88-levels and lengths."""
    fields: list[LayoutField] = []
    pending: list[OrrorhCondition] = []
    current_88_name: str | None = None
    current_88_values: list[str] = []
    started = False
    active = False
    want = (start_field or "").strip().upper()

    def flush_88() -> None:
        nonlocal current_88_name, current_88_values
        if current_88_name:
            pending.append(OrrorhCondition(current_88_name, tuple(current_88_values)))
        current_88_name = None
        current_88_values = []

    def finish_field() -> None:
        flush_88()
        if fields and active and pending:
            last = fields[-1]
            fields[-1] = LayoutField(
                last.name, last.length, tuple(pending), last.skip
            )
        pending.clear()

    for raw in copybook_text.splitlines():
        if _is_comment_line(raw):
            continue
        body = _copybook_body(raw)
        if not body.strip():
            continue

        pic = _PIC_LINE_RE.search(raw)
        if pic:
            finish_field()
            level = int(pic.group(1))
            name = pic.group(2).strip().upper()
            try:
                length = pic_storage_length(pic.group(3))
            except ValueError:
                active = False
                continue
            if level == 88:
                active = False
                continue
            skip = FILLER_TOKEN in name
            if not started:
                if name != want:
                    active = False
                    continue
                started = True
            fields.append(LayoutField(name, length, (), skip))
            active = True
            continue

        if not started or not fields or not active:
            continue

        level88 = _LEVEL88_RE.match(body.lstrip())
        if level88:
            flush_88()
            current_88_name = level88.group(1).strip().upper()
            current_88_values = _cobol_literals(body)
            continue
        if current_88_name:
            extra = _cobol_literals(body)
            if extra:
                current_88_values.extend(extra)

    finish_field()
    return fields


@lru_cache(maxsize=4)
def load_pic_copybook(name: str, start_field: str) -> tuple[LayoutField, ...]:
    path = copybooks_dir() / name
    text = path.read_text(encoding="utf-8", errors="replace")
    return tuple(parse_pic_copybook(text, start_field=start_field))


def map_fixed_width_record(
    record: str,
    fields: list[LayoutField] | tuple[LayoutField, ...],
) -> list[dict]:
    """Slice a fixed-width record by PIC lengths. Empty slices become Spaces."""
    text = record or ""
    offset = 0
    payload: list[dict] = []
    for field in fields:
        raw = text[offset : offset + field.length]
        offset += field.length
        if field.skip:
            continue
        stripped = raw.strip()
        value = stripped if stripped else SPACES_VALUE
        item: dict = {"name": field.name, "value": value}
        if field.conditions:
            item["conditions"] = [
                {
                    "name": condition.name,
                    "values": [
                        SPACES_VALUE if literal.strip() == "" else literal
                        for literal in condition.values
                    ],
                    "matched": condition_matches(condition.values, value),
                }
                for condition in field.conditions
            ]
        payload.append(item)
    return payload


def numbered_report_lines(fields: list[dict]) -> list[str]:
    return [
        f"{index}. {item['name']} = {item['value']}"
        for index, item in enumerate(fields, start=1)
    ]
