from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from error_analysis.config import Settings
from error_analysis.datadog.client import DatadogClient
from error_analysis.datadog.models import LogSearchFilter, LogSearchParams
from error_analysis.datadog.query_builder import build_checkout_query
from error_analysis.datadog.search import search_logs

COPYBOOK_START_FIELD = "ORRORH-REQUEST-FUNCTION"
IGNORED_FIELD_PREFIXES = ("ORRORD-",)
FILLER_TOKEN = "FILLER"

# XML tag names that differ slightly from the copybook field name.
XML_TAG_ALIASES: dict[str, tuple[str, ...]] = {
    "ORRORH-CC-FIRST-NAME": ("ORRORH-CC-FIRST-NAME-INITIAL",),
    "ORRORH-EU-SHIP-CTAC-NAME": ("ORRORH-EU-SHIP-CTAC-NAM",),
    "ORRORH-ORDER-FTZ-FLAG-SW": ("ORRORH-ORDER-FTZ-FLAG",),
}

SPACES_VALUE = "Spaces"
SUBSTATION_MARKER = "Substation Request"
ORDER_UPDATE_SERVICE = "OrderUpdate_Service_root"
SUBSTATION_LOG_DESCRIPTION = "OrderCreateCallSubstationRequest"
V2_SERVICE_PREFIX = "OrderCreate_v2"

_PIC_FIELD_RE = re.compile(
    r"^\s*(?:\d{6})?\s*(\d{2})\s+(ORRORH-[A-Z0-9-]+)\s+PIC\b",
    re.IGNORECASE,
)
_LEVEL88_RE = re.compile(
    r"^\s*88\s+(ORRORH-[A-Z0-9-]+)\b",
    re.IGNORECASE,
)
_SEQ_PREFIX_RE = re.compile(r"^\d{6}")
_TRAILING_MARK_RE = re.compile(r"\s+[A-Z]{2,4}\d{5}\s*$")
_LITERAL_RE = re.compile(r"'([^']*)'")
_COMMENT_SEQ_RE = re.compile(r"^\d{6}\*")
_XML_TAG_RE = re.compile(
    r"<(?:\w+:)?(ORRORH-[A-Z0-9-]+)(?:\s[^>/]*)?(?:/>|>(.*?)</(?:\w+:)?\1>)",
    re.IGNORECASE | re.DOTALL,
)
_SS_OPEN_RE = re.compile(r"<(?:\w+:)?SSOrderEntryRequest\b", re.IGNORECASE)
_SS_CLOSE_RE = re.compile(r"</(?:\w+:)?SSOrderEntryRequest>", re.IGNORECASE)
_SERVICE_NAME_RE = re.compile(
    r"<(?:\w+:)?ServiceName>(.*?)</(?:\w+:)?ServiceName>",
    re.IGNORECASE | re.DOTALL,
)
_LOG_DESC_RE = re.compile(
    r"<(?:\w+:)?LogDescription>(.*?)</(?:\w+:)?LogDescription>",
    re.IGNORECASE | re.DOTALL,
)


def copybook_path() -> Path:
    return Path(__file__).resolve().parents[1] / "copybooks" / "ORRORH"


def _is_comment_line(line: str) -> bool:
    if _COMMENT_SEQ_RE.match(line):
        return True
    if len(line) > 6 and line[:6].isdigit() and line[6] == "*":
        return True
    body = re.sub(r"^\d{6}", "", line)
    return body.lstrip().startswith("*")


def _copybook_body(line: str) -> str:
    """Drop sequence numbers and trailing change-mark tokens (e.g. ROR10293)."""
    text = _SEQ_PREFIX_RE.sub("", line, count=1)
    return _TRAILING_MARK_RE.sub("", text).rstrip()


def _cobol_literals(text: str) -> list[str]:
    return [match.group(1) for match in _LITERAL_RE.finditer(text or "")]


@dataclass(frozen=True)
class OrrorhCondition:
    """88-level condition-name attached to the preceding PIC field."""

    name: str
    values: tuple[str, ...]


@dataclass(frozen=True)
class OrrorhCopybookField:
    name: str
    conditions: tuple[OrrorhCondition, ...] = ()


def parse_orrorh_copybook(copybook_text: str) -> list[OrrorhCopybookField]:
    """Elementary ORRORH PIC fields with attached 88 condition-names.

    Starts at ``ORRORH-REQUEST-FUNCTION``. Skips comments, FILLER, group items
    without PIC, and ORRORD-*. 88 VALUE literals may continue on the next line.
    """
    fields: list[OrrorhCopybookField] = []
    pending_conditions: list[OrrorhCondition] = []
    current_88_name: str | None = None
    current_88_values: list[str] = []
    started = False
    active = False

    def flush_88() -> None:
        nonlocal current_88_name, current_88_values
        if current_88_name:
            pending_conditions.append(
                OrrorhCondition(current_88_name, tuple(current_88_values))
            )
        current_88_name = None
        current_88_values = []

    def finish_field() -> None:
        flush_88()
        if fields and active and pending_conditions:
            last = fields[-1]
            fields[-1] = OrrorhCopybookField(last.name, tuple(pending_conditions))
        pending_conditions.clear()

    for raw in copybook_text.splitlines():
        if _is_comment_line(raw):
            continue
        body = _copybook_body(raw)
        if not body.strip():
            continue

        pic = _PIC_FIELD_RE.search(raw)
        if pic:
            finish_field()
            level = int(pic.group(1))
            name = pic.group(2).strip().upper()
            if level == 88:
                active = False
                continue
            if FILLER_TOKEN in name or name.startswith(IGNORED_FIELD_PREFIXES):
                active = False
                continue
            if not started:
                if name != COPYBOOK_START_FIELD:
                    active = False
                    continue
                started = True
            fields.append(OrrorhCopybookField(name, ()))
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


def parse_orrorh_fields(copybook_text: str) -> list[str]:
    """Elementary ORRORH PIC field names, starting at ``ORRORH-REQUEST-FUNCTION``."""
    return [field.name for field in parse_orrorh_copybook(copybook_text)]


@lru_cache(maxsize=1)
def orrorh_copybook_model() -> tuple[OrrorhCopybookField, ...]:
    path = copybook_path()
    text = path.read_text(encoding="utf-8", errors="replace")
    return tuple(parse_orrorh_copybook(text))


@lru_cache(maxsize=1)
def orrorh_copybook_fields() -> tuple[str, ...]:
    return tuple(field.name for field in orrorh_copybook_model())


def condition_matches(values: tuple[str, ...] | list[str], field_value: str) -> bool:
    """True when the PIC field value satisfies a COBOL 88 VALUE set."""
    current = "" if (field_value or "") == SPACES_VALUE else (field_value or "")
    for literal in values:
        if literal.strip() == "":
            if current == "":
                return True
            continue
        if current == literal:
            return True
    return False


def _condition_payload(
    field: OrrorhCopybookField, value: str
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for condition in field.conditions:
        display_values = [
            SPACES_VALUE if literal.strip() == "" else literal
            for literal in condition.values
        ]
        items.append(
            {
                "name": condition.name,
                "values": display_values,
                "matched": condition_matches(condition.values, value),
            }
        )
    return items


def extract_substation_xml(text: str) -> str:
    """Return the ``SSOrderEntryRequest`` XML from a Substation Request payload.

    Datadog often truncates huge ``ORRORD-DETAIL-ELEMENTS`` payloads, so the
    closing ``</SSOrderEntryRequest>`` tag may be missing. In that case keep
    everything from the open tag to the end of the indexed text — header
    ``ORRORH-*`` fields still parse.
    """
    if not text or not isinstance(text, str):
        return ""
    unescaped = html.unescape(text)
    start = _SS_OPEN_RE.search(unescaped)
    if not start:
        return ""
    end = _SS_CLOSE_RE.search(unescaped, start.start())
    if end:
        return unescaped[start.start() : end.end()]
    return unescaped[start.start() :]


def parse_orrorh_xml_values(xml_text: str) -> dict[str, str]:
    """Map ``ORRORH-*`` tags to inner text. Empty / self-closing tags are omitted."""
    values: dict[str, str] = {}
    for match in _XML_TAG_RE.finditer(xml_text or ""):
        name = match.group(1).strip().upper()
        if name.startswith(IGNORED_FIELD_PREFIXES):
            continue
        inner = match.group(2)
        if inner is None:
            continue
        stripped = html.unescape(inner).strip()
        if stripped:
            values[name] = stripped
    return values


def lookup_field_value(field: str, xml_values: dict[str, str]) -> str:
    key = (field or "").strip().upper()
    if key in xml_values:
        return xml_values[key]
    for alias in XML_TAG_ALIASES.get(key, ()):
        if alias in xml_values:
            return xml_values[alias]
    return SPACES_VALUE


def build_orrorh_report_lines(
    xml_text: str,
    *,
    fields: list[str] | tuple[str, ...] | None = None,
) -> list[str]:
    """Numbered ``FIELD = value`` lines from the copybook vs Substation XML."""
    names = list(fields if fields is not None else orrorh_copybook_fields())
    xml_values = parse_orrorh_xml_values(xml_text)
    lines: list[str] = []
    for index, name in enumerate(names, start=1):
        value = lookup_field_value(name, xml_values)
        lines.append(f"{index}. {name} = {value}")
    return lines


def build_orrorh_report_fields(
    xml_text: str,
    *,
    model: list[OrrorhCopybookField] | tuple[OrrorhCopybookField, ...] | None = None,
) -> list[dict[str, Any]]:
    """Copybook fields with XML values and 88 condition-names."""
    entries = list(model if model is not None else orrorh_copybook_model())
    xml_values = parse_orrorh_xml_values(xml_text)
    payload: list[dict[str, Any]] = []
    for field in entries:
        value = lookup_field_value(field.name, xml_values)
        item: dict[str, Any] = {"name": field.name, "value": value}
        conditions = _condition_payload(field, value)
        if conditions:
            item["conditions"] = conditions
        payload.append(item)
    return payload


def format_orrorh_report(xml_text: str) -> str:
    return "\n".join(build_orrorh_report_lines(xml_text))


@dataclass(frozen=True)
class OrrorhLookupResult:
    report: str
    fields: list[dict[str, Any]]
    xml: str
    v2_found: bool
    source_log_id: str | None
    comment_records: list[dict[str, Any]] = field(default_factory=list)
    line_records: list[dict[str, Any]] = field(default_factory=list)


_EVENT_STRING_KEYS = (
    "RequestLogPayload",
    "requestLogPayload",
    "message",
    "content",
    "LogDescription",
    "ServiceName",
    "service",
    "CorrelationId",
    "correlationId",
    "correlation_id",
)


def _event_strings(event: dict[str, Any]) -> list[str]:
    chunks: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        text = html.unescape(value)
        if not text.strip() or text in seen:
            return
        seen.add(text)
        chunks.append(text)

    attributes = event.get("attributes") if isinstance(event, dict) else None
    nested = attributes.get("attributes") if isinstance(attributes, dict) else None
    for container in (nested, attributes, event):
        if not isinstance(container, dict):
            continue
        for key in _EVENT_STRING_KEYS:
            value = container.get(key)
            if isinstance(value, str):
                add(value)
        for value in container.values():
            if not isinstance(value, str):
                continue
            if (
                "SSOrderEntryRequest" in value
                or SUBSTATION_MARKER in value
                or SUBSTATION_LOG_DESCRIPTION in value
                or "ORRORH-" in value
            ):
                add(value)
    return chunks


def _joined_event_text(event: dict[str, Any]) -> str:
    return "\n".join(_event_strings(event))


def _event_service(event: dict[str, Any]) -> str:
    attributes = event.get("attributes") if isinstance(event, dict) else None
    if isinstance(attributes, dict):
        nested = attributes.get("attributes")
        if isinstance(nested, dict):
            service = nested.get("service")
            if isinstance(service, str) and service.strip():
                return service.strip()
        service = attributes.get("service")
        if isinstance(service, str) and service.strip():
            return service.strip()
    service = event.get("service") if isinstance(event, dict) else None
    if isinstance(service, str):
        return service.strip()
    return ""


def is_order_create_v2_event(event: dict[str, Any], order_number: str) -> bool:
    """True when the log is OrderCreate_v2_0 for the resubmitted customer PO."""
    po = (order_number or "").strip()
    if not po:
        return False
    text = _joined_event_text(event)
    if po not in text:
        return False
    service = _event_service(event)
    if service.startswith(V2_SERVICE_PREFIX):
        return True
    if V2_SERVICE_PREFIX in text:
        return True
    named = _SERVICE_NAME_RE.search(text)
    if named and V2_SERVICE_PREFIX in named.group(1):
        return True
    return False


def is_order_update_substation_event(event: dict[str, Any]) -> bool:
    """True for OrderUpdate Substation Request logs.

    TIBCO writes ``ServiceName`` / ``LogDescription`` inside the log XML.
    Datadog's ``service:`` facet is often unset, so do not require it.
    """
    text = _joined_event_text(event)
    if SUBSTATION_LOG_DESCRIPTION in text or SUBSTATION_MARKER in text:
        return True
    if "SSOrderEntryRequest" in text:
        return True
    desc = _LOG_DESC_RE.search(text)
    return bool(desc and SUBSTATION_LOG_DESCRIPTION in desc.group(1))


def extract_substation_xml_from_event(event: dict[str, Any]) -> str:
    for chunk in _event_strings(event):
        if SUBSTATION_MARKER not in chunk and "SSOrderEntryRequest" not in chunk:
            continue
        xml = extract_substation_xml(chunk)
        if xml:
            return xml
    return extract_substation_xml(_joined_event_text(event))


def xml_matches_order_number(xml_text: str, order_number: str) -> bool:
    po = (order_number or "").strip()
    return bool(po) and po in (xml_text or "")


def event_matches_order_number(
    event: dict[str, Any],
    order_number: str,
    xml_text: str = "",
) -> bool:
    """True when the customer PO appears in Substation XML or log text.

    OrderUpdate CorrelationId concatenates PO + timestamp
    (``P279513762026-10-02T01:00:43.459-07:00``), so a substring match on
    the event text still hits when the XML body is truncated.
    """
    po = (order_number or "").strip()
    if not po:
        return False
    if po in (xml_text or ""):
        return True
    return po in _joined_event_text(event)


def report_from_substation_xml(xml_text: str) -> OrrorhLookupResult:
    from error_analysis.order_create.detail_elements import (
        parse_detail_elements_from_xml,
    )

    fields = build_orrorh_report_fields(xml_text)
    lines = [
        f"{index}. {item['name']} = {item['value']}"
        for index, item in enumerate(fields, start=1)
    ]
    comments, line_records = parse_detail_elements_from_xml(xml_text)
    return OrrorhLookupResult(
        report="\n".join(lines),
        fields=fields,
        xml=xml_text,
        v2_found=False,
        source_log_id=None,
        comment_records=comments,
        line_records=line_records,
    )


def empty_orrorh_result(*, v2_found: bool = False) -> OrrorhLookupResult:
    return OrrorhLookupResult(
        report="",
        fields=[],
        xml="",
        v2_found=v2_found,
        source_log_id=None,
        comment_records=[],
        line_records=[],
    )


def orrorh_api_payload(result: OrrorhLookupResult) -> dict[str, Any]:
    return {
        "orrorhReport": result.report,
        "orrorhFields": result.fields,
        "orrorhV2Found": result.v2_found,
        "orrorhSourceLogId": result.source_log_id,
        "orrorcRecords": result.comment_records,
        "orrorlRecords": result.line_records,
    }


def build_substation_search_query(
    po: str,
    *,
    extra_terms: str | None = None,
    service: str | None = None,
) -> str:
    """AND the PO with extra keywords without phrase-quoting the whole string.

    ``build_checkout_query`` quotes multi-word ``search_text`` as one phrase.
    ``P27951376`` and ``OrderCreateCallSubstationRequest`` are not adjacent in
    TIBCO logs, so that phrase matches nothing.
    """
    query = build_checkout_query(search_text=po, service=service)
    extra = (extra_terms or "").strip()
    if extra:
        return f"{query} {extra}"
    return query


def _can_wildcard_po(po: str) -> bool:
    stripped = (po or "").strip()
    if not stripped or any(ch.isspace() for ch in stripped):
        return False
    return not any(ch in stripped for ch in '*?"')


def _search_events(
    client: DatadogClient,
    settings: Settings,
    *,
    search_text: str,
    service: str | None,
    from_time: str,
    to_time: str,
    extra_terms: str | None = None,
) -> list[dict[str, Any]]:
    query = build_substation_search_query(
        search_text,
        extra_terms=extra_terms,
        service=service,
    )
    params = LogSearchParams(
        filter=LogSearchFilter(
            query=query,
            **{"from": from_time, "to": to_time},
            storage_tier=settings.default_storage_tier,
        ),
        sort=settings.default_sort,
        page_limit=settings.default_page_limit,
    )
    return list(search_logs(client, params))


def find_v2_event(
    events: list[dict[str, Any]], order_number: str
) -> dict[str, Any] | None:
    for event in events:
        if is_order_create_v2_event(event, order_number):
            return event
    return None


def find_substation_xml(
    events: list[dict[str, Any]], order_number: str
) -> tuple[str, str | None]:
    for event in events:
        xml = extract_substation_xml_from_event(event)
        if not xml:
            continue
        if order_number and not event_matches_order_number(
            event, order_number, xml
        ):
            continue
        log_id = event.get("id")
        return xml, str(log_id) if log_id else None
    return "", None


def lookup_orrorh_from_events(
    *,
    v2_events: list[dict[str, Any]],
    update_events: list[dict[str, Any]],
    order_number: str,
) -> OrrorhLookupResult:
    v2_event = find_v2_event(v2_events, order_number)
    xml, log_id = find_substation_xml(update_events, order_number)
    if not xml:
        return empty_orrorh_result(v2_found=v2_event is not None)
    result = report_from_substation_xml(xml)
    return OrrorhLookupResult(
        report=result.report,
        fields=result.fields,
        xml=xml,
        v2_found=v2_event is not None,
        source_log_id=log_id,
        comment_records=result.comment_records,
        line_records=result.line_records,
    )


def fetch_orrorh_lookup(
    client: DatadogClient,
    settings: Settings,
    *,
    order_number: str,
    from_time: str,
    to_time: str,
    env: str | None = None,
) -> OrrorhLookupResult:
    """Find OrderCreate_v2_0 then OrderUpdate_Service_root Substation Request."""
    del env  # reserved for callers that already scoped the Datadog window
    po = (order_number or "").strip()
    if not po:
        return empty_orrorh_result()

    v2_events = _search_events(
        client,
        settings,
        search_text=po,
        service="OrderCreate_v2*",
        from_time=from_time,
        to_time=to_time,
    )

    attempts: list[tuple[str, str | None, str | None]] = [
        # Do not require service:OrderUpdate_Service_root — ServiceName is XML.
        (po, SUBSTATION_LOG_DESCRIPTION, None),
        (po, f'"{SUBSTATION_MARKER}"', None),
    ]
    if _can_wildcard_po(po):
        # CorrelationId is PO+timestamp, e.g. P279513762026-10-02T01:00:43.459
        attempts.append((f"{po}*", SUBSTATION_LOG_DESCRIPTION, None))
    attempts.append((po, None, None))

    update_events: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    last = empty_orrorh_result(v2_found=find_v2_event(v2_events, po) is not None)
    for search_text, extra_terms, service in attempts:
        batch = _search_events(
            client,
            settings,
            search_text=search_text,
            extra_terms=extra_terms,
            service=service,
            from_time=from_time,
            to_time=to_time,
        )
        for event in batch:
            event_id = str(event.get("id") or "")
            key = event_id or str(id(event))
            if key in seen_ids:
                continue
            seen_ids.add(key)
            update_events.append(event)
        last = lookup_orrorh_from_events(
            v2_events=v2_events,
            update_events=update_events,
            order_number=po,
        )
        if last.xml:
            return last
    return last
