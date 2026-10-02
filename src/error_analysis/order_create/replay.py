from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from error_analysis.config import Settings
from error_analysis.datadog.client import DatadogClient
from error_analysis.datadog.errors import DatadogError
from error_analysis.logging_config import get_logger
from error_analysis.datadog.fetch_request import (
    fetch_request_records,
    resolve_service_filter,
)
from error_analysis.order_create.curl_builder import (
    OrderCreateCurl,
    OrderCreateCurlError,
    build_order_create_curl_from_records,
    format_order_create_curl,
)
from error_analysis.order_create.curl_parser import parse_order_create_curl
from error_analysis.order_create.order_number import (
    apply_order_number,
    customer_order_number_from_body,
    resolve_replay_order_number,
)
from error_analysis.error_lookup.client import corora_code_from_statuscode
from error_analysis.order_create.response_check import (
    ResponseCheckResult,
    build_error_report,
    build_result_payload,
    build_success_summary,
    check_from_http_body,
    extract_globalorderid,
    find_globalorderid_in_records,
    find_response_check,
    find_two_char_statuscode_in_sources,
    is_impulse_order_number,
    is_v6_response_service,
)

logger = get_logger("order_create.replay")

# After a REST SUCCESS, Datadog may still hold the clubbed Impulse Order Number
# (30-Q6HX2). Keep this short so Re-Submit stays close to Postman speed.
IMPULSE_LOOKUP_POLL_INTERVAL = 2.0
IMPULSE_LOOKUP_TIMEOUT = 12.0


@dataclass(frozen=True)
class ReplayResult:
    customer_order_number: str
    original_order_number: str
    url: str
    http_status: int | None
    http_body: Any
    records: list[dict[str, Any]]
    check: ResponseCheckResult | None
    summary: dict[str, Any] | None
    outcome: str  # SUCCESS | FAILED | TIMEOUT | UNKNOWN
    curl: str = ""


def default_time_window() -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(minutes=15)
    end = now + timedelta(minutes=5)
    return (
        start.isoformat().replace("+00:00", "Z"),
        end.isoformat().replace("+00:00", "Z"),
    )


def default_search_window(days: int = 30) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    return (
        start.isoformat().replace("+00:00", "Z"),
        now.isoformat().replace("+00:00", "Z"),
    )


def _authorization_header(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _write_json(path: Path, payload: dict[str, Any] | list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, default=str, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def post_order_create(
    *,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    username: str,
    password: str,
    timeout: float = 60.0,
    authorization: str | None = None,
) -> tuple[int, Any]:
    request_headers = dict(headers)
    if authorization and authorization.strip():
        request_headers["Authorization"] = authorization.strip()
    else:
        request_headers["Authorization"] = _authorization_header(username, password)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.post(url, headers=request_headers, json=body)
    except httpx.ConnectError as exc:
        host = httpx.URL(url).host or url
        raise OrderCreateCurlError(
            f"Cannot reach Order Create host {host!r} "
            f"(DNS/network error: {exc}). "
            "Connect to the corporate VPN and retry."
        ) from exc
    except httpx.RequestError as exc:
        host = httpx.URL(url).host or url
        raise OrderCreateCurlError(
            f"Order Create request to {host!r} failed: {exc}"
        ) from exc
    try:
        parsed: Any = response.json()
    except ValueError:
        parsed = response.text
    return response.status_code, parsed


def rebuild_curl_with_body(
    built: OrderCreateCurl,
    body: dict[str, Any],
    *,
    username: str,
    password: str,
) -> str:
    return format_order_create_curl(
        url=built.url,
        headers=built.headers,
        body=body,
        username=username,
        password=password,
        redact_password=False,
    )


def poll_response_logs(
    client: DatadogClient,
    settings: Settings,
    *,
    order_number: str,
    from_time: str,
    to_time: str,
    poll_interval: float,
    timeout: float,
    env: str | None = None,
) -> list[dict[str, Any]]:
    """Poll Datadog until a ResponseLogPayload with responsepreamble appears or timeout.

    When a FAILED response carries a numeric statuscode (e.g. 400), keep polling
    for a short grace window: the OrderCreate_v2 XML log with the two-char CORORA
    code (e.g. D9) is often indexed a few seconds after the JSON response log.
    Similarly, when the best response so far is not from an OrderCreate_v6*
    service, wait a grace window for the authoritative v6 'OrderCreate Response
    formed' log (it must win over sibling note logs, e.g. WY address notes).
    """
    deadline = time.monotonic() + timeout
    last_records: list[dict[str, Any]] = []
    service = resolve_service_filter(settings)
    grace_deadline: float | None = None

    while True:
        fetched = fetch_request_records(
            client,
            settings,
            from_time=from_time,
            to_time=to_time,
            text=order_number,
            env=env,
            service=service,
        )
        last_records = fetched.records
        check = find_response_check(last_records)
        if check is not None:
            needs_two_char = check.outcome == "FAILED" and not corora_code_from_statuscode(
                check.statuscode
            )
            needs_v6 = not is_v6_response_service(check.source_service)
            # On SUCCESS the impulse order number may land in a slightly later
            # log (e.g. the v2 XML response); wait a grace window for it.
            needs_impulse = check.outcome == "SUCCESS" and not is_impulse_order_number(
                check.globalorderid or find_globalorderid_in_records(last_records)
            )
            if not needs_two_char and not needs_v6 and not needs_impulse:
                return last_records
            if grace_deadline is None:
                grace_deadline = min(
                    deadline, time.monotonic() + max(2 * poll_interval, 30.0)
                )
            if time.monotonic() >= grace_deadline:
                return last_records
        elif time.monotonic() >= deadline:
            return last_records
        time.sleep(poll_interval)


def poll_impulse_order_id(
    client: DatadogClient,
    settings: Settings,
    *,
    order_number: str,
    from_time: str,
    to_time: str,
    poll_interval: float,
    timeout: float,
    env: str | None = None,
) -> list[dict[str, Any]]:
    """Poll Datadog until a clubbed Impulse Order Number appears (e.g. 30-Q6HX2)."""
    deadline = time.monotonic() + timeout
    last_records: list[dict[str, Any]] = []
    service = resolve_service_filter(settings)

    while True:
        fetched = fetch_request_records(
            client,
            settings,
            from_time=from_time,
            to_time=to_time,
            text=order_number,
            env=env,
            service=service,
        )
        last_records = fetched.records
        if is_impulse_order_number(find_globalorderid_in_records(last_records)):
            return last_records
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return last_records
        time.sleep(min(poll_interval, remaining))


def poll_corora_statuscode(
    client: DatadogClient,
    settings: Settings,
    *,
    order_number: str,
    from_time: str,
    to_time: str,
    poll_interval: float,
    timeout: float,
    env: str | None = None,
) -> list[dict[str, Any]]:
    """Poll Datadog until ResponseLogPayload XML has a CORORA statuscode."""
    deadline = time.monotonic() + timeout
    last_records: list[dict[str, Any]] = []
    service = resolve_service_filter(settings)

    while True:
        fetched = fetch_request_records(
            client,
            settings,
            from_time=from_time,
            to_time=to_time,
            text=order_number,
            env=env,
            service=service,
        )
        last_records = fetched.records
        if find_two_char_statuscode_in_sources(records=last_records):
            return last_records
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return last_records
        time.sleep(min(poll_interval, remaining))


def _resolve_impulse_order_id(
    records: list[dict[str, Any]],
    http_body: Any,
    current: str = "",
) -> str:
    if is_impulse_order_number(current):
        return str(current).strip()
    for candidate in (
        find_globalorderid_in_records(records),
        extract_globalorderid(http_body),
    ):
        if is_impulse_order_number(candidate):
            return candidate
    return ""


def _enrich_impulse_from_datadog(
    settings: Settings,
    *,
    check: ResponseCheckResult,
    order_number: str,
    from_time: str | None,
    to_time: str | None,
    env: str | None,
) -> tuple[list[dict[str, Any]], ResponseCheckResult]:
    """Fill clubbed Impulse Order Number from Datadog after a REST SUCCESS."""
    if is_impulse_order_number(check.globalorderid):
        return [], check
    try:
        window_from, window_to = default_time_window()
        with DatadogClient(settings) as client:
            records = poll_impulse_order_id(
                client,
                settings,
                order_number=order_number,
                from_time=from_time or window_from,
                to_time=to_time or window_to,
                poll_interval=IMPULSE_LOOKUP_POLL_INTERVAL,
                timeout=IMPULSE_LOOKUP_TIMEOUT,
                env=env,
            )
    except DatadogError as exc:
        logger.warning("Impulse order lookup skipped: %s", exc)
        return [], check
    except Exception as exc:
        logger.warning("Impulse order lookup failed: %s", exc)
        return [], check

    impulse = find_globalorderid_in_records(records)
    if is_impulse_order_number(impulse):
        check = replace(check, globalorderid=impulse)
    return records, check


def _enrich_corora_from_datadog(
    settings: Settings,
    *,
    check: ResponseCheckResult,
    order_number: str,
    from_time: str | None,
    to_time: str | None,
    env: str | None,
) -> tuple[list[dict[str, Any]], ResponseCheckResult]:
    """Fill FAILED Code from Datadog ``<tns:statuscode>`` (LULAEN → EN)."""
    mapped = corora_code_from_statuscode(check.statuscode)
    if mapped:
        if mapped != (check.statuscode or "").strip():
            check = replace(check, statuscode=mapped)
        return [], check
    try:
        window_from, window_to = default_time_window()
        with DatadogClient(settings) as client:
            records = poll_corora_statuscode(
                client,
                settings,
                order_number=order_number,
                from_time=from_time or window_from,
                to_time=to_time or window_to,
                poll_interval=IMPULSE_LOOKUP_POLL_INTERVAL,
                timeout=IMPULSE_LOOKUP_TIMEOUT,
                env=env,
            )
    except DatadogError as exc:
        logger.warning("FAILED statuscode lookup skipped: %s", exc)
        return [], check
    except Exception as exc:
        logger.warning("FAILED statuscode lookup failed: %s", exc)
        return [], check

    code = find_two_char_statuscode_in_sources(
        records=records,
        response_payload=check.response_payload
        if isinstance(check.response_payload, dict)
        else None,
    )
    if code:
        check = replace(check, statuscode=code)
    return records, check


def _finalize_artifacts(
    out_dir: Path | None,
    summary: dict[str, Any],
    *,
    write_error_report: bool = False,
) -> None:
    if out_dir is None:
        return
    _write_json(out_dir / "order-create-result.json", summary)
    _write_json(out_dir / "order-create-replay-summary.json", summary)
    if write_error_report:
        _write_json(out_dir / "order-create-error-report.json", summary)


def _complete_replay(
    *,
    settings: Settings,
    url: str,
    headers: dict[str, str],
    new_body: dict[str, Any],
    new_number: str,
    original: str,
    curl_text: str,
    from_time: str | None,
    to_time: str | None,
    poll_interval: float,
    timeout: float,
    env: str | None,
    out_dir: Path | None,
    source_search_text: str | None,
    authorization: str | None = None,
    wait_for_logs: bool = True,
) -> ReplayResult:
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        _write_json(out_dir / "order-create-replay-body.json", new_body)
        (out_dir / "order-create-replay.curl.txt").write_text(
            curl_text + "\n",
            encoding="utf-8",
        )

    http_status, http_body = post_order_create(
        url=url,
        headers=headers,
        body=new_body,
        username=settings.order_create_username,
        password=settings.order_create_password,
        authorization=authorization,
    )

    fetched_records: list[dict[str, Any]] = []
    if wait_for_logs:
        window_from, window_to = default_time_window()
        poll_from = from_time or window_from
        poll_to = to_time or window_to
        with DatadogClient(settings) as client:
            fetched_records = poll_response_logs(
                client,
                settings,
                order_number=new_number,
                from_time=poll_from,
                to_time=poll_to,
                poll_interval=poll_interval,
                timeout=timeout,
                env=env,
            )
        check = find_response_check(fetched_records)
    else:
        check = check_from_http_body(http_body, http_status=http_status)
        if (
            check is not None
            and check.outcome == "SUCCESS"
            and not is_impulse_order_number(check.globalorderid)
        ):
            fetched_records, check = _enrich_impulse_from_datadog(
                settings,
                check=check,
                order_number=new_number,
                from_time=from_time,
                to_time=to_time,
                env=env,
            )
        elif check is not None and check.outcome == "FAILED":
            fetched_records, check = _enrich_corora_from_datadog(
                settings,
                check=check,
                order_number=new_number,
                from_time=from_time,
                to_time=to_time,
                env=env,
            )

    if out_dir is not None:
        _write_json(out_dir / "order-create-replay-logs.json", fetched_records)

    if check is None:
        if wait_for_logs:
            outcome = "TIMEOUT"
            message = "No ResponseLogPayload with responsepreamble found before timeout."
        else:
            outcome = "UNKNOWN"
            message = "Order Create HTTP response had no responsepreamble."
        summary = build_result_payload(
            outcome=outcome,
            customer_order_number=new_number,
            original_customer_order_number=original,
            source_search_text=source_search_text,
            http_status=http_status,
            http_body=http_body,
            message=message,
        )
        _finalize_artifacts(out_dir, summary)
        return ReplayResult(
            customer_order_number=new_number,
            original_order_number=original,
            url=url,
            http_status=http_status,
            http_body=http_body,
            records=fetched_records,
            check=None,
            summary=summary,
            outcome=outcome,
            curl=curl_text,
        )

    if check.outcome == "FAILED":
        summary = build_error_report(
            customer_order_number=new_number,
            check=check,
            http_status=http_status,
            original_customer_order_number=original,
            source_search_text=source_search_text,
        )
        summary["http_body"] = http_body
        impulse = _resolve_impulse_order_id(
            fetched_records, http_body, str(summary.get("globalorderid") or "")
        )
        if impulse:
            summary["globalorderid"] = impulse
        elif not is_impulse_order_number(summary.get("globalorderid")):
            summary["globalorderid"] = ""
        _finalize_artifacts(out_dir, summary, write_error_report=True)
        return ReplayResult(
            customer_order_number=new_number,
            original_order_number=original,
            url=url,
            http_status=http_status,
            http_body=http_body,
            records=fetched_records,
            check=check,
            summary=summary,
            outcome="FAILED",
            curl=curl_text,
        )

    if check.outcome == "SUCCESS":
        summary = build_success_summary(
            customer_order_number=new_number,
            check=check,
            http_status=http_status,
            original_customer_order_number=original,
            source_search_text=source_search_text,
        )
        # Prefer Datadog/clubbed Impulse Order Number (30-Q6HX2) over REST
        # numeric ingramOrderNumber (7109517746).
        impulse = _resolve_impulse_order_id(
            fetched_records, http_body, str(summary.get("globalorderid") or "")
        )
        if impulse:
            summary["globalorderid"] = impulse
        elif not is_impulse_order_number(summary.get("globalorderid")):
            summary["globalorderid"] = ""
        _finalize_artifacts(out_dir, summary)
        return ReplayResult(
            customer_order_number=new_number,
            original_order_number=original,
            url=url,
            http_status=http_status,
            http_body=http_body,
            records=fetched_records,
            check=check,
            summary=summary,
            outcome="SUCCESS",
            curl=curl_text,
        )

    summary = build_result_payload(
        outcome="UNKNOWN",
        customer_order_number=new_number,
        original_customer_order_number=original,
        source_search_text=source_search_text,
        statuscode=check.statuscode,
        responsemessage=check.responsemessage,
        errorcode=check.errorcode,
        responsestatus=check.responsestatus,
        globalorderid=check.globalorderid,
        http_status=http_status,
        source_log_id=check.source_log_id,
        response_payload=check.response_payload,
        http_body=http_body,
    )
    _finalize_artifacts(out_dir, summary)
    return ReplayResult(
        customer_order_number=new_number,
        original_order_number=original,
        url=url,
        http_status=http_status,
        http_body=http_body,
        records=fetched_records,
        check=check,
        summary=summary,
        outcome="UNKNOWN",
        curl=curl_text,
    )


def run_replay(
    settings: Settings,
    records: list[dict[str, Any]],
    *,
    index: int = 0,
    order_number: str | None = None,
    use_random: bool = False,
    from_time: str | None = None,
    to_time: str | None = None,
    poll_interval: float = 15.0,
    timeout: float = 180.0,
    env: str | None = None,
    out_dir: Path | None = None,
    source_search_text: str | None = None,
    target: str | None = None,
) -> ReplayResult:
    if not settings.order_create_username.strip():
        raise OrderCreateCurlError(
            "ORDER_CREATE_USERNAME is required in .env for replay-order."
        )
    if not settings.order_create_password:
        raise OrderCreateCurlError(
            "ORDER_CREATE_PASSWORD is required in .env for replay-order."
        )

    built = build_order_create_curl_from_records(
        records,
        username=settings.order_create_username,
        password=settings.order_create_password,
        redact_password=False,
        index=index,
        cookie=settings.order_create_cookie or None,
        target=target,
    )

    original = customer_order_number_from_body(built.body)
    if not original:
        raise OrderCreateCurlError(
            "Order Create body is missing customerOrderNumber."
        )
    new_number = resolve_replay_order_number(
        original,
        explicit=order_number,
        use_random=use_random,
    )
    new_body = apply_order_number(built.body, new_number)
    curl_text = rebuild_curl_with_body(
        built,
        new_body,
        username=settings.order_create_username,
        password=settings.order_create_password,
    )

    return _complete_replay(
        settings=settings,
        url=built.url,
        headers=built.headers,
        new_body=new_body,
        new_number=new_number,
        original=original,
        curl_text=curl_text,
        from_time=from_time,
        to_time=to_time,
        poll_interval=poll_interval,
        timeout=timeout,
        env=env,
        out_dir=out_dir,
        source_search_text=source_search_text,
    )


def run_replay_from_curl(
    settings: Settings,
    curl_text: str,
    *,
    use_random: bool = False,
    order_number: str | None = None,
    from_time: str | None = None,
    to_time: str | None = None,
    poll_interval: float = 15.0,
    timeout: float = 180.0,
    env: str | None = None,
    out_dir: Path | None = None,
    source_search_text: str | None = None,
    wait_for_logs: bool = True,
) -> ReplayResult:
    """Parse an edited curl, bump/randomize customerOrderNumber, then POST.

    When ``wait_for_logs`` is true (CLI replay-order), poll Datadog for the
    response preamble. UI Re-Submit sets it false so the call returns as soon
    as the Order Create HTTP response arrives, like Postman.
    """
    parsed = parse_order_create_curl(curl_text)

    original = customer_order_number_from_body(parsed.body)
    if not original:
        raise OrderCreateCurlError(
            "Order Create body is missing customerOrderNumber."
        )
    new_number = resolve_replay_order_number(
        original,
        explicit=order_number,
        use_random=use_random,
    )
    new_body = apply_order_number(parsed.body, new_number)

    username = settings.order_create_username or "user"
    password = settings.order_create_password or ""
    # Prefer .env credentials for Authorization rewrite; fall back to curl Authorization.
    if username.strip() and password:
        rebuilt_curl = format_order_create_curl(
            url=parsed.url,
            headers=parsed.headers,
            body=new_body,
            username=username,
            password=password,
            redact_password=False,
        )
        authorization = None
    else:
        rebuilt_curl = format_order_create_curl(
            url=parsed.url,
            headers=parsed.headers,
            body=new_body,
            username="user",
            password="",
            redact_password=True,
        )
        # Keep Auth from the edited curl when .env credentials are missing.
        authorization = parsed.authorization
        if not authorization:
            raise OrderCreateCurlError(
                "ORDER_CREATE_USERNAME/PASSWORD or Authorization header is required."
            )

    return _complete_replay(
        settings=settings,
        url=parsed.url,
        headers=parsed.headers,
        new_body=new_body,
        new_number=new_number,
        original=original,
        curl_text=rebuilt_curl,
        from_time=from_time,
        to_time=to_time,
        poll_interval=poll_interval,
        timeout=timeout,
        env=env,
        out_dir=out_dir,
        source_search_text=source_search_text,
        authorization=authorization,
        wait_for_logs=wait_for_logs,
    )
