from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlparse

from error_analysis.datadog.models import ParsedDatadogUrl, ms_to_iso

STORAGE_MAP = {
    "hot": "indexes",
    "indexes": "indexes",
    "flex": "flex",
    "online-archives": "online-archives",
}


def parse_datadog_logs_url(url: str) -> ParsedDatadogUrl:
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    def first(key: str) -> str | None:
        values = params.get(key)
        return values[0] if values else None

    query = first("query")
    if query is not None:
        query = unquote(query)

    from_time: str | None = None
    to_time: str | None = None

    from_ts = first("from_ts")
    to_ts = first("to_ts")
    if from_ts and from_ts.isdigit():
        from_time = ms_to_iso(int(from_ts))
    if to_ts and to_ts.isdigit():
        to_time = ms_to_iso(int(to_ts))

    if not from_time:
        from_time = first("from")
    if not to_time:
        to_time = first("to")

    storage = first("storage") or "hot"
    storage_tier = STORAGE_MAP.get(storage, "indexes")

    stream_sort = first("stream_sort") or "desc"
    sort = "-timestamp" if stream_sort == "desc" else "timestamp"

    display_fields: list[str] = []
    cols = first("cols")
    if cols:
        display_fields = [c.strip() for c in unquote(cols).split(",") if c.strip()]

    return ParsedDatadogUrl(
        query=query,
        from_time=from_time,
        to_time=to_time,
        storage_tier=storage_tier,
        sort=sort,
        display_fields=display_fields,
    )
