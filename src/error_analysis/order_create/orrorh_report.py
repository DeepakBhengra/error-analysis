from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import datetime
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
ORDER_UPDATE_SERVICE_FILTER = "OrderUpdate_Service*"
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
_DATE_TIMESTAMP_RE = re.compile(
    r"<(?:\w+:)?DateTimestamp>(.*?)</(?:\w+:)?DateTimestamp>",
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


CUSTOMER_PO_FIELDS = (
    "ORRORH-CUST-TO-ING-PO-NBR",
    "ORRORH-CUST-TO-CUST-PO-NBR",
)
INGRAM_ORDER_NBR_FIELD = "ORRORH-INGRAM-ORDER-NBR"
CUSTOMER_BR_FIELD = "ORRORH-CUSTOMER-BR"
CUSTOMER_NBR_FIELD = "ORRORH-CUSTOMER-NBR"
_UNKNOWN_TIMESTAMP_DELTA_MS = 2**62


@dataclass(frozen=True)
class CurlIdentity:
    """Customer identity taken from the Order Create curl / source log."""

    po: str = ""
    br: str = ""
    nbr: str = ""
    timestamp_ms: int | None = None


def parse_timestamp_ms(value: Any) -> int | None:
    """Parse Datadog / ISO / epoch timestamps to milliseconds."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        if number > 1e12:
            return int(number)
        if number > 1e9:
            return int(number * 1000)
        return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.isdigit():
        return parse_timestamp_ms(int(text))
    iso = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(iso)
    except ValueError:
        return None
    return int(parsed.timestamp() * 1000)


def event_timestamp_ms(event: dict[str, Any]) -> int | None:
    """Datadog ``attributes.timestamp``, else TIBCO ``DateTimestamp``."""
    attributes = event.get("attributes") if isinstance(event, dict) else None
    nested = attributes.get("attributes") if isinstance(attributes, dict) else None
    for container in (nested, attributes, event):
        if not isinstance(container, dict):
            continue
        parsed = parse_timestamp_ms(container.get("timestamp"))
        if parsed is not None:
            return parsed
    text = _joined_event_text(event) if isinstance(event, dict) else ""
    match = _DATE_TIMESTAMP_RE.search(text)
    if not match:
        return None
    return parse_timestamp_ms(match.group(1).strip())


def parse_customer_br_nbr(value: str) -> tuple[str, str]:
    """Split ``41-008922`` or compact ``41008922`` into BR + NBR."""
    text = (value or "").strip()
    if not text:
        return "", ""
    if "-" in text:
        branch, number = text.split("-", 1)
        return branch.strip(), number.strip()
    compact = re.sub(r"\s+", "", text)
    if len(compact) >= 3:
        return compact[:2], compact[2:]
    return "", ""


def _header_value(headers: dict[str, Any] | None, name: str) -> str:
    if not isinstance(headers, dict):
        return ""
    wanted = name.lower()
    for key, value in headers.items():
        if str(key).lower() == wanted and isinstance(value, str):
            return value.strip()
    return ""


def curl_identity_from_order_create(
    *,
    headers: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
    timestamp: Any = None,
    fallback_po: str = "",
) -> CurlIdentity:
    """Read customer PO / BR / NBR from the built curl and optional log time."""
    po = (fallback_po or "").strip()
    if isinstance(body, dict):
        body_po = body.get("customerOrderNumber")
        if isinstance(body_po, str) and body_po.strip():
            po = body_po.strip()
    customer = _header_value(headers, "IM-CustomerNumber")
    branch, number = parse_customer_br_nbr(customer)
    if (not branch or not number) and isinstance(body, dict):
        reseller = body.get("resellerInfo")
        reseller_id = reseller.get("resellerId") if isinstance(reseller, dict) else None
        if isinstance(reseller_id, str) and reseller_id.strip():
            parsed_br, parsed_nbr = parse_customer_br_nbr(reseller_id.strip())
            branch = branch or parsed_br
            number = number or parsed_nbr
    return CurlIdentity(
        po=po,
        br=branch,
        nbr=number,
        timestamp_ms=parse_timestamp_ms(timestamp),
    )


def _token_equal(left: str, right: str) -> bool:
    return (left or "").strip().upper() == (right or "").strip().upper()


def _nbr_equal(left: str, right: str) -> bool:
    if _token_equal(left, right):
        return True
    a = (left or "").strip()
    b = (right or "").strip()
    if a.isdigit() and b.isdigit():
        return (a.lstrip("0") or "0") == (b.lstrip("0") or "0")
    return False


def xml_matches_order_number(xml_text: str, order_number: str) -> bool:
    po = (order_number or "").strip()
    return bool(po) and po in (xml_text or "")


def _field_matches_po(value: str, po: str) -> bool:
    text = (value or "").strip()
    return bool(text) and (text == po or po in text)


def xml_customer_po_matches(xml_text: str, order_number: str) -> bool:
    """True when a customer PO tag equals or contains the searched PO."""
    po = (order_number or "").strip()
    if not po:
        return False
    values = parse_orrorh_xml_values(xml_text)
    return any(_field_matches_po(values.get(name, ""), po) for name in CUSTOMER_PO_FIELDS)


def xml_ingram_order_matches(xml_text: str, order_number: str) -> bool:
    """True when ``ORRORH-INGRAM-ORDER-NBR`` equals or contains the search text."""
    po = (order_number or "").strip()
    if not po:
        return False
    values = parse_orrorh_xml_values(xml_text)
    return _field_matches_po(values.get(INGRAM_ORDER_NBR_FIELD, ""), po)


def xml_customer_br_nbr_contradicts(
    xml_text: str, identity: CurlIdentity | None
) -> bool:
    """True when Substation BR/NBR are present and disagree with the curl."""
    if identity is None or (not identity.br and not identity.nbr):
        return False
    values = parse_orrorh_xml_values(xml_text)
    xml_br = (values.get(CUSTOMER_BR_FIELD) or "").strip()
    xml_nbr = (values.get(CUSTOMER_NBR_FIELD) or "").strip()
    if identity.br and xml_br and not _token_equal(identity.br, xml_br):
        return True
    if identity.nbr and xml_nbr and not _nbr_equal(identity.nbr, xml_nbr):
        return True
    return False


def xml_customer_br_nbr_matches(
    xml_text: str, identity: CurlIdentity | None
) -> bool:
    """True when curl BR and NBR both appear on the Substation header."""
    if identity is None or not identity.br or not identity.nbr:
        return False
    values = parse_orrorh_xml_values(xml_text)
    xml_br = (values.get(CUSTOMER_BR_FIELD) or "").strip()
    xml_nbr = (values.get(CUSTOMER_NBR_FIELD) or "").strip()
    return bool(
        xml_br
        and xml_nbr
        and _token_equal(identity.br, xml_br)
        and _nbr_equal(identity.nbr, xml_nbr)
    )


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


def _substation_candidate_score(
    xml_text: str,
    order_number: str,
    identity: CurlIdentity | None = None,
) -> int:
    """Rank a Substation XML body for a customer-PO search.

    Customer PO tags outrank a bare substring match (CorrelationId).
    An Ingram order number that happens to equal the search text is rejected
    so ``12948`` does not attach ``60-SZ1840`` when the curl is ``41-008922``.
    When curl BR/NBR are known, a contradicting header is rejected and an
    exact BR+NBR match outranks PO-only hits.
    """
    if xml_customer_br_nbr_contradicts(xml_text, identity):
        return 0
    identity_customer = xml_customer_br_nbr_matches(xml_text, identity)
    if xml_customer_po_matches(xml_text, order_number):
        score = 400 if identity_customer else 200
    elif xml_ingram_order_matches(xml_text, order_number):
        return 0
    elif identity_customer:
        score = 150
    else:
        score = 50
    from error_analysis.order_create.detail_elements import (
        extract_detail_elements,
        first_detail_record_start,
    )

    if first_detail_record_start(extract_detail_elements(xml_text)) >= 0:
        score += 10
    return score


def _timestamp_delta_ms(
    event: dict[str, Any], identity: CurlIdentity | None
) -> int | None:
    if identity is None or identity.timestamp_ms is None:
        return None
    event_ts = event_timestamp_ms(event)
    if event_ts is None:
        return _UNKNOWN_TIMESTAMP_DELTA_MS
    return abs(event_ts - identity.timestamp_ms)


def find_substation_xml(
    events: list[dict[str, Any]],
    order_number: str,
    identity: CurlIdentity | None = None,
) -> tuple[str, str | None]:
    """Return the Substation XML that best matches the curl identity."""
    po = (identity.po if identity and identity.po else order_number) or ""
    best_xml = ""
    best_id: str | None = None
    best_score = 0
    best_delta: int | None = None
    for event in events:
        xml = extract_substation_xml_from_event(event)
        if not xml:
            continue
        if po and not event_matches_order_number(event, po, xml):
            continue
        score = _substation_candidate_score(xml, po, identity)
        if score <= 0:
            continue
        delta = _timestamp_delta_ms(event, identity)
        closer = (
            delta is not None
            and (best_delta is None or delta < best_delta)
        )
        if score > best_score or (score == best_score and closer):
            best_score = score
            best_delta = delta
            best_xml = xml
            log_id = event.get("id")
            best_id = str(log_id) if log_id else None
    return best_xml, best_id


def lookup_orrorh_from_events(
    *,
    v2_events: list[dict[str, Any]],
    update_events: list[dict[str, Any]],
    order_number: str,
    identity: CurlIdentity | None = None,
) -> OrrorhLookupResult:
    po = (identity.po if identity and identity.po else order_number) or ""
    v2_event = find_v2_event(v2_events, po)
    xml, log_id = find_substation_xml(
        update_events, po, identity=identity
    )
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
    identity: CurlIdentity | None = None,
) -> OrrorhLookupResult:
    """Find OrderCreate_v2_0 then OrderUpdate_Service_root Substation Request."""
    del env  # reserved for callers that already scoped the Datadog window
    po = (order_number or "").strip()
    if identity and identity.po and not po:
        po = identity.po
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
        # Datadog service facet when present (OrderUpdate_Service / _root).
        (po, SUBSTATION_LOG_DESCRIPTION, ORDER_UPDATE_SERVICE_FILTER),
        (po, f'"{SUBSTATION_MARKER}"', ORDER_UPDATE_SERVICE_FILTER),
        (po, None, ORDER_UPDATE_SERVICE_FILTER),
        # ServiceName is often only inside TIBCO XML, so also search without it.
        (po, SUBSTATION_LOG_DESCRIPTION, None),
        (po, f'"{SUBSTATION_MARKER}"', None),
    ]
    if _can_wildcard_po(po):
        # CorrelationId is PO+timestamp, e.g. P279513762026-10-02T01:00:43.459
        attempts.append(
            (f"{po}*", SUBSTATION_LOG_DESCRIPTION, ORDER_UPDATE_SERVICE_FILTER)
        )
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
            identity=identity,
        )
        if last.xml:
            return last
    return last
