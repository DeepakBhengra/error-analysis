from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

from error_analysis.config import Settings
from error_analysis.datadog.client import DatadogClient
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
    resolve_replay_order_number,
)
from error_analysis.error_lookup.client import is_two_char_error_code
from error_analysis.order_create.response_check import (
    ResponseCheckResult,
    build_error_report,
    build_result_payload,
    build_success_summary,
    extract_globalorderid,
    find_globalorderid_in_records,
    find_response_check,
    is_v6_response_service,
)


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
            needs_two_char = check.outcome == "FAILED" and not is_two_char_error_code(
                check.statuscode
            )
            needs_v6 = not is_v6_response_service(check.source_service)
            # On SUCCESS the impulse order number may land in a slightly later
            # log (e.g. the v2 XML response); wait a grace window for it.
            needs_impulse = check.outcome == "SUCCESS" and not (
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

    if out_dir is not None:
        _write_json(out_dir / "order-create-replay-logs.json", fetched_records)

    check = find_response_check(fetched_records)
    if check is None:
        summary = build_result_payload(
            outcome="TIMEOUT",
            customer_order_number=new_number,
            original_customer_order_number=original,
            source_search_text=source_search_text,
            http_status=http_status,
            http_body=http_body,
            message="No ResponseLogPayload with responsepreamble found before timeout.",
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
            outcome="TIMEOUT",
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
        if not str(summary.get("globalorderid") or "").strip():
            fallback_id = find_globalorderid_in_records(
                fetched_records
            ) or extract_globalorderid(http_body)
            if fallback_id:
                summary["globalorderid"] = fallback_id
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
        # The classified log may omit the impulse order number; look in the
        # other fetched logs, then the immediate HTTP response body.
        if not str(summary.get("globalorderid") or "").strip():
            fallback_id = find_globalorderid_in_records(
                fetched_records
            ) or extract_globalorderid(http_body)
            if fallback_id:
                summary["globalorderid"] = fallback_id
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

    original = built.body.get("customerOrderNumber")
    if not isinstance(original, str) or not original.strip():
        raise OrderCreateCurlError(
            "Order Create body is missing customerOrderNumber."
        )
    original = original.strip()
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
) -> ReplayResult:
    """Parse an edited curl, bump/randomize customerOrderNumber, POST + poll."""
    parsed = parse_order_create_curl(curl_text)

    original = parsed.body.get("customerOrderNumber")
    if not isinstance(original, str) or not original.strip():
        raise OrderCreateCurlError(
            "Order Create body is missing customerOrderNumber."
        )
    original = original.strip()
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
    )
