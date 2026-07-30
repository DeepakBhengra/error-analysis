from __future__ import annotations

import re

DEFAULT_ORDER_CREATE_SERVICES: tuple[str, ...] = (
    "AsyncOrderCreate",
    "OrderCreate_v6*",
    "OrderCreate_v2*",
)

# Datadog free-text indexing splits on '/'; keeping it inside a quoted
# phrase (e.g. "115669/2026 MI PB") often returns zero hits even when the
# PO is present in RequestLogPayload. Do not treat '_' as a separator —
# service names like OrderCreate_v6_0 are searched as-is.
_SEARCH_TOKEN_SEPARATORS = re.compile(r"[/\\]+")
_MULTI_SPACE = re.compile(r"\s+")


def _format_search_term(value: str) -> str:
    """Format a term like the Datadog Logs search bar (free-text by default).

    Customer POs such as ``115669/2026 MI PB`` are normalized so ``/`` becomes
    a space before quoting. Datadog tokenizes on ``/``, so a literal slash
    inside quotes fails to match the indexed tokens ``115669`` ``2026`` ``MI``
    ``PB``.
    """
    stripped = value.strip()
    if not stripped:
        return stripped
    if stripped.startswith('"') and stripped.endswith('"'):
        return stripped

    normalized = _SEARCH_TOKEN_SEPARATORS.sub(" ", stripped)
    normalized = _MULTI_SPACE.sub(" ", normalized).strip()
    if any(ch.isspace() for ch in normalized):
        return f'"{normalized}"'
    return normalized


def _normalize_services(
    service: str | list[str] | tuple[str, ...] | None,
) -> list[str]:
    if service is None:
        return []
    if isinstance(service, str):
        parts = [part.strip() for part in service.split(",")]
        return [part for part in parts if part]
    return [str(item).strip() for item in service if str(item).strip()]


def _normalize_hosts(
    host: str | list[str] | tuple[str, ...] | None,
) -> list[str]:
    if host is None:
        return []
    if isinstance(host, str):
        parts = [part.strip() for part in host.split(",")]
        return [part for part in parts if part]
    return [str(item).strip() for item in host if str(item).strip()]


def format_service_filter(services: list[str]) -> str | None:
    """Build a Datadog service filter for one or more services."""
    if not services:
        return None
    if len(services) == 1:
        return f"service:{services[0]}"
    joined = " OR ".join(services)
    return f"service:({joined})"


def format_host_filter(hosts: list[str]) -> str | None:
    """Build a Datadog host filter for one or more hosts."""
    if not hosts:
        return None
    if len(hosts) == 1:
        return f"host:{hosts[0]}"
    joined = " OR ".join(hosts)
    return f"host:({joined})"


def build_checkout_query(
    *,
    search_text: str | None = None,
    correlation_id: str | None = None,
    job_id: str | None = None,
    customer_po: str | None = None,
    env: str | None = None,
    service: str | list[str] | tuple[str, ...] | None = DEFAULT_ORDER_CREATE_SERVICES,
    host: str | list[str] | tuple[str, ...] | None = None,
) -> str:
    """Build a Datadog logs query.

    ``search_text`` is free-text (Datadog Logs search bar).
    Default service filter is AsyncOrderCreate OR OrderCreate_v6* OR OrderCreate_v2*
    (wildcards match the versioned prod services, e.g. OrderCreate_v6_1).
    """
    terms: list[str] = []

    for value in (search_text, correlation_id, job_id, customer_po):
        if value and value.strip():
            terms.append(_format_search_term(value))

    if not terms:
        raise ValueError(
            "At least one of search_text, correlation_id, job_id, or customer_po is required"
        )

    service_filter = format_service_filter(_normalize_services(service))
    if service_filter:
        terms.append(service_filter)
    host_filter = format_host_filter(_normalize_hosts(host))
    if host_filter:
        terms.append(host_filter)
    if env and env.strip():
        terms.append(f"env:{env.strip()}")

    return " ".join(terms)
