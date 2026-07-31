from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import httpx
import typer

from error_analysis.config import Settings, get_settings
from error_analysis.datadog.client import DatadogClient
from error_analysis.datadog.errors import DatadogAuthError, DatadogError
from error_analysis.datadog.fetch_request import (
    fetch_request_records,
    resolve_service_filter,
)
from error_analysis.datadog.models import LogSearchFilter, LogSearchParams
from error_analysis.datadog.search import search_logs
from error_analysis.datadog.url_parser import parse_datadog_logs_url
from error_analysis.extractors.request_log_payload import (
    build_result_record,
    extract_request_log_payload,
)
from error_analysis.logging_config import get_logger, setup_logging
from error_analysis.order_create.curl_builder import (
    OrderCreateCurlError,
    build_order_create_curl_from_records,
    find_order_create_records,
)
from error_analysis.order_create.pair_mining import (
    default_training_window,
    default_validation_window,
    mine_pairs,
    run_report,
)
from error_analysis.order_create.replay import default_time_window, run_replay

app = typer.Typer(
    name="error-analysis",
    help="Fetch checkout Hermes request payloads from Datadog logs.",
    no_args_is_help=True,
)

logger = get_logger("cli")


@app.callback()
def _cli_main(
    log_level: Optional[str] = typer.Option(
        None,
        "--log-level",
        help="Logging level (DEBUG, INFO, WARNING, ERROR). Default: ERROR_ANALYSIS_LOG_LEVEL or INFO.",
        envvar="ERROR_ANALYSIS_LOG_LEVEL",
    ),
) -> None:
    """Configure application logging for CLI commands."""
    log_dir = setup_logging(level=log_level)
    logger.debug("CLI logging ready (log_dir=%s)", log_dir)


def _load_settings() -> Settings:
    try:
        return get_settings()
    except Exception as exc:
        logger.exception("Configuration error while loading settings")
        typer.secho(
            f"Configuration error: {exc}\nCopy .env.example to .env and set DD_API_KEY / DD_APP_KEY.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1) from exc


@app.command()
def validate() -> None:
    """Validate Datadog API credentials."""
    settings = _load_settings()
    with DatadogClient(settings) as client:
        try:
            result = client.validate_credentials()
        except DatadogAuthError as exc:
            logger.error("Datadog credentials invalid: %s", exc)
            typer.secho(f"Invalid credentials: {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from exc
        except DatadogError as exc:
            logger.error("Datadog validation failed: %s", exc)
            typer.secho(f"Validation failed: {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from exc

    valid = result.get("valid", False)
    if valid:
        typer.secho("Credentials are valid.", fg=typer.colors.GREEN)
    else:
        logger.warning("Unexpected Datadog validation response: %s", result)
        typer.secho(f"Unexpected validation response: {result}", fg=typer.colors.YELLOW)


@app.command()
def fetch(
    url: Optional[str] = typer.Option(None, "--url", help="Datadog Logs Explorer URL"),
    query: Optional[str] = typer.Option(None, "--query", help="Log search query"),
    from_time: Optional[str] = typer.Option(
        None, "--from", help="Start time (ISO-8601)"
    ),
    to_time: Optional[str] = typer.Option(None, "--to", help="End time (ISO-8601)"),
    storage_tier: Optional[str] = typer.Option(
        None, "--storage-tier", help="Storage tier (indexes, flex, online-archives)"
    ),
    sort: Optional[str] = typer.Option(None, "--sort", help="Sort order"),
    limit: Optional[int] = typer.Option(None, "--limit", help="Page size (max 1000)"),
    payload_path: Optional[str] = typer.Option(
        None,
        "--payload-path",
        help="Dot-path to RequestLogPayload in log event",
    ),
    out: Optional[Path] = typer.Option(
        None, "--out", help="Output JSON file path"
    ),
) -> None:
    """Search Datadog logs and extract RequestLogPayload."""
    settings = _load_settings()

    parsed_url = parse_datadog_logs_url(url) if url else None

    final_query = query or (parsed_url.query if parsed_url else None) or settings.default_query
    final_from = from_time or (parsed_url.from_time if parsed_url else None)
    final_to = to_time or (parsed_url.to_time if parsed_url else None)
    final_storage = (
        storage_tier
        or (parsed_url.storage_tier if parsed_url else None)
        or settings.default_storage_tier
    )
    final_sort = sort or (parsed_url.sort if parsed_url else None) or settings.default_sort
    final_limit = limit or settings.default_page_limit

    if not final_from or not final_to:
        typer.secho(
            "Time range required. Provide --from/--to or a Datadog URL with from_ts/to_ts.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    params = LogSearchParams(
        filter=LogSearchFilter(
            query=final_query,
            **{"from": final_from, "to": final_to},
            storage_tier=final_storage,
        ),
        sort=final_sort,
        page_limit=final_limit,
        display_fields=parsed_url.display_fields if parsed_url else [],
    )

    results: list[dict] = []
    missing_payload = 0
    total_logs = 0

    with DatadogClient(settings) as client:
        try:
            for event in search_logs(client, params):
                total_logs += 1
                payload = extract_request_log_payload(event, payload_path=payload_path)
                if payload is None:
                    missing_payload += 1
                    continue
                results.append(build_result_record(event, payload))
        except DatadogError as exc:
            typer.secho(f"Fetch failed: {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from exc

    output = json.dumps(results, indent=2, default=str)

    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(output, encoding="utf-8")
        typer.secho(f"Wrote {len(results)} records to {out}", fg=typer.colors.GREEN)
    else:
        sys.stdout.write(output + "\n")

    typer.secho(
        f"Summary: {total_logs} logs scanned, "
        f"{len(results)} payloads extracted, "
        f"{missing_payload} logs missing payload.",
        fg=typer.colors.CYAN,
        err=True,
    )


@app.command("fetch-request")
def fetch_request(
    text: Optional[str] = typer.Option(
        None,
        "--text",
        "-t",
        help="Free-text Datadog search (Logs search bar), e.g. bw0a101orlv or DEEPAKDDTEST1",
    ),
    correlation_id: Optional[str] = typer.Option(
        None,
        "--correlation-id",
        help="Correlation ID filter only (do not use for free-text search)",
    ),
    job_id: Optional[str] = typer.Option(None, "--job-id", help="Job ID to search"),
    customer_po: Optional[str] = typer.Option(
        None, "--customer-po", help="Customer PO number to search"
    ),
    from_time: str = typer.Option(..., "--from", help="Start time (ISO-8601)"),
    to_time: str = typer.Option(..., "--to", help="End time (ISO-8601)"),
    env: Optional[str] = typer.Option(
        None, "--env", help="Optional environment filter (e.g. uat, prod)"
    ),
    service: Optional[str] = typer.Option(
        None,
        "--service",
        help=(
            "Service filter override (comma-separated). "
            "Default: OrderCreate_v6,OrderCreate_v2"
        ),
    ),
    no_service_filter: bool = typer.Option(
        False,
        "--no-service-filter",
        help="Do not add service: filter (match plain Datadog search bar)",
    ),
    limit: Optional[int] = typer.Option(None, "--limit", help="Page size (max 1000)"),
    out: Optional[Path] = typer.Option(None, "--out", help="Output JSON file path"),
) -> None:
    """Search Datadog logs with free-text and extract Hermes request JSON."""
    if not any(
        value and value.strip()
        for value in (text, correlation_id, job_id, customer_po)
    ):
        typer.secho(
            "Provide at least one of --text, --correlation-id, --job-id, or --customer-po.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    settings = _load_settings()
    resolved_service = resolve_service_filter(
        settings,
        service=service,
        no_service_filter=no_service_filter,
    )

    with DatadogClient(settings) as client:
        try:
            fetched = fetch_request_records(
                client,
                settings,
                from_time=from_time,
                to_time=to_time,
                text=text,
                correlation_id=correlation_id,
                job_id=job_id,
                customer_po=customer_po,
                env=env,
                service=resolved_service,
                limit=limit,
            )
        except ValueError as exc:
            typer.secho(str(exc), fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from exc
        except DatadogError as exc:
            typer.secho(f"Fetch failed: {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from exc

    typer.secho(f"Query: {fetched.query}", fg=typer.colors.BLUE, err=True)

    output = json.dumps(fetched.records, indent=2, default=str)

    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(output, encoding="utf-8")
        typer.secho(
            f"Wrote {len(fetched.records)} records to {out}",
            fg=typer.colors.GREEN,
        )
    else:
        sys.stdout.write(output + "\n")

    typer.secho(
        f"Summary: {fetched.total_logs} logs scanned, "
        f"{len(fetched.records)} records extracted "
        f"({fetched.request_count} with request, "
        f"{fetched.response_count} with ResponseLogPayload), "
        f"{fetched.missing_payload} logs missing request/response payload.",
        fg=typer.colors.CYAN,
        err=True,
    )


@app.command("build-order-curl")
def build_order_curl(
    from_file: Path = typer.Option(
        ...,
        "--from-file",
        help="JSON file of Datadog fetch-request records (array)",
    ),
    index: Optional[int] = typer.Option(
        None,
        "--index",
        help="0-based index among matching Order Create records (default: first)",
    ),
    out: Optional[Path] = typer.Option(
        None,
        "--out",
        help="Optional path to write the request body JSON",
    ),
    redact_password: bool = typer.Option(
        False,
        "--redact-password",
        help="Replace Authorization Basic token with *** (for safe sharing)",
    ),
    target: str = typer.Option(
        "uat",
        "--target",
        help="Order Create endpoint for AsyncOrderCreate bodies: uat or qa",
    ),
) -> None:
    """Build an Order Create Postman/curl from a mapped Datadog Order Create record."""
    settings = _load_settings()
    if not settings.order_create_username.strip():
        typer.secho(
            "ORDER_CREATE_USERNAME is required in .env for build-order-curl.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)
    if not redact_password and not settings.order_create_password:
        typer.secho(
            "ORDER_CREATE_PASSWORD is required in .env "
            "(or pass --redact-password to emit Basic ***).",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    try:
        raw = json.loads(from_file.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        typer.secho(f"File not found: {from_file}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    except json.JSONDecodeError as exc:
        typer.secho(f"Invalid JSON in {from_file}: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc

    if not isinstance(raw, list):
        typer.secho(
            f"{from_file} must contain a JSON array of Datadog records.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    matches = find_order_create_records(
        [item for item in raw if isinstance(item, dict)]
    )
    if not matches:
        typer.secho(
            "No AsyncOrderCreate, OrderCreate_v6/uschileai2503, "
            "or mapped OrderCreate_v2 body record found.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    selected_index = 0 if index is None else index
    if selected_index < 0 or selected_index >= len(matches):
        typer.secho(
            f"--index {selected_index} out of range "
            f"(0..{len(matches) - 1}; {len(matches)} matching body record(s)).",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    try:
        built = build_order_create_curl_from_records(
            [item for item in raw if isinstance(item, dict)],
            username=settings.order_create_username,
            password=settings.order_create_password,
            redact_password=redact_password,
            index=selected_index,
            cookie=settings.order_create_cookie or None,
            target=target,
        )
    except OrderCreateCurlError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc

    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(built.body, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        typer.secho(f"Wrote request body to {out}", fg=typer.colors.GREEN, err=True)

    typer.secho(
        f"body service={built.body_service} host={built.body_host} "
        f"headers from service={built.header_service} host={built.header_host} "
        f"url={built.url}",
        fg=typer.colors.CYAN,
        err=True,
    )
    sys.stdout.write(built.curl + "\n")


@app.command("replay-order")
def replay_order(
    text: Optional[str] = typer.Option(
        None,
        "--text",
        "-t",
        help="Search Datadog for this customer order number, then replay",
    ),
    from_file: Optional[Path] = typer.Option(
        None,
        "--from-file",
        help="JSON file of Datadog fetch-request records (array)",
    ),
    search_from: Optional[str] = typer.Option(
        None,
        "--search-from",
        help="Source Datadog search start (ISO-8601); required with --text",
    ),
    search_to: Optional[str] = typer.Option(
        None,
        "--search-to",
        help="Source Datadog search end (ISO-8601); required with --text",
    ),
    out_dir: Path = typer.Option(
        Path("results"),
        "--out-dir",
        help="Directory for replay body, logs, and reports",
    ),
    order_number: Optional[str] = typer.Option(
        None,
        "--order-number",
        help="Explicit customerOrderNumber (default: trailing digit +1)",
    ),
    random_order: bool = typer.Option(
        False,
        "--random",
        help="Use a random customerOrderNumber instead of bumping",
    ),
    index: Optional[int] = typer.Option(
        None,
        "--index",
        help="0-based index among matching Order Create records (default: first)",
    ),
    from_time: Optional[str] = typer.Option(
        None,
        "--from",
        help="Post-replay Datadog poll start (ISO-8601); default now-15m UTC",
    ),
    to_time: Optional[str] = typer.Option(
        None,
        "--to",
        help="Post-replay Datadog poll end (ISO-8601); default now+5m UTC",
    ),
    poll_interval: float = typer.Option(
        15.0,
        "--poll-interval",
        help="Seconds between Datadog polls for ResponseLogPayload",
    ),
    timeout: float = typer.Option(
        180.0,
        "--timeout",
        help="Max seconds to wait for ResponseLogPayload",
    ),
    env: Optional[str] = typer.Option(
        None, "--env", help="Optional environment filter (e.g. uat)"
    ),
    target: str = typer.Option(
        "uat",
        "--target",
        help="Order Create endpoint for AsyncOrderCreate bodies: uat or qa",
    ),
) -> None:
    """Search (or load) Order Create logs, replay with a new order number, store result."""
    has_text = bool(text and text.strip())
    has_file = from_file is not None
    if has_text == has_file:
        typer.secho(
            "Provide exactly one of --text or --from-file.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    if order_number and random_order:
        typer.secho(
            "Use only one of --order-number or --random.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)

    settings = _load_settings()
    source_search_text: str | None = None
    records: list[dict]

    if has_text:
        assert text is not None
        if not search_from or not search_to:
            typer.secho(
                "--search-from and --search-to are required when using --text.",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(1)
        source_search_text = text.strip()
        resolved_service = resolve_service_filter(settings)
        typer.secho(
            f"Fetching source logs for text={source_search_text!r}",
            fg=typer.colors.BLUE,
            err=True,
        )
        with DatadogClient(settings) as client:
            try:
                fetched = fetch_request_records(
                    client,
                    settings,
                    from_time=search_from,
                    to_time=search_to,
                    text=source_search_text,
                    env=env,
                    service=resolved_service,
                )
            except ValueError as exc:
                typer.secho(str(exc), fg=typer.colors.RED, err=True)
                raise typer.Exit(1) from exc
            except DatadogError as exc:
                typer.secho(f"Fetch failed: {exc}", fg=typer.colors.RED, err=True)
                raise typer.Exit(1) from exc

        typer.secho(f"Query: {fetched.query}", fg=typer.colors.BLUE, err=True)
        if not fetched.records:
            typer.secho(
                f"No Order Create request/response records found for {source_search_text!r}.",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(1)

        out_dir.mkdir(parents=True, exist_ok=True)
        source_path = out_dir / "order-create-source-logs.json"
        source_path.write_text(
            json.dumps(fetched.records, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        typer.secho(
            f"Wrote {len(fetched.records)} source records to {source_path}",
            fg=typer.colors.GREEN,
            err=True,
        )
        records = fetched.records
    else:
        assert from_file is not None
        try:
            raw = json.loads(from_file.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            typer.secho(f"File not found: {from_file}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from exc
        except json.JSONDecodeError as exc:
            typer.secho(
                f"Invalid JSON in {from_file}: {exc}",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(1) from exc

        if not isinstance(raw, list):
            typer.secho(
                f"{from_file} must contain a JSON array of Datadog records.",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(1)

        records = [item for item in raw if isinstance(item, dict)]
        for item in records:
            search_text = item.get("search_text")
            if isinstance(search_text, str) and search_text.strip():
                source_search_text = search_text.strip()
                break

    selected_index = 0 if index is None else index
    poll_from, poll_to = default_time_window()
    typer.secho(
        f"Replaying Order Create "
        f"(order-number={'explicit' if order_number else 'random' if random_order else 'bump+1'})",
        fg=typer.colors.BLUE,
        err=True,
    )

    try:
        result = run_replay(
            settings,
            records,
            index=selected_index,
            order_number=order_number,
            use_random=random_order,
            from_time=from_time or poll_from,
            to_time=to_time or poll_to,
            poll_interval=poll_interval,
            timeout=timeout,
            env=env,
            out_dir=out_dir,
            source_search_text=source_search_text,
            target=target,
        )
    except OrderCreateCurlError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    except DatadogError as exc:
        typer.secho(f"Datadog fetch failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    except httpx.HTTPError as exc:
        typer.secho(f"Order Create HTTP failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc

    typer.secho(
        f"customerOrderNumber {result.original_order_number} -> "
        f"{result.customer_order_number} | HTTP {result.http_status} | "
        f"outcome={result.outcome}",
        fg=typer.colors.CYAN,
        err=True,
    )
    typer.secho(
        f"Wrote result to {out_dir / 'order-create-result.json'}",
        fg=typer.colors.CYAN,
        err=True,
    )

    if result.outcome == "SUCCESS":
        typer.secho(
            "RequestLogPayload ran successfully "
            f"(statuscode={result.check.statuscode if result.check else ''}, "
            f"responsemessage={result.check.responsemessage if result.check else ''}).",
            fg=typer.colors.GREEN,
        )
        raise typer.Exit(0)

    if result.outcome == "FAILED":
        check = result.check
        typer.secho(
            "Order Create FAILED in ResponseLogPayload: "
            f"statuscode={check.statuscode if check else ''} "
            f"responsemessage={check.responsemessage if check else ''}",
            fg=typer.colors.RED,
            err=True,
        )
        typer.secho(
            f"Wrote error report to {out_dir / 'order-create-error-report.json'}",
            fg=typer.colors.YELLOW,
            err=True,
        )
        raise typer.Exit(1)

    if result.outcome == "TIMEOUT":
        typer.secho(
            "Timed out waiting for ResponseLogPayload with responsepreamble.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(2)

    typer.secho(
        "ResponseLogPayload found but outcome is unknown "
        f"(statuscode={result.check.statuscode if result.check else ''}, "
        f"responsemessage={result.check.responsemessage if result.check else ''}).",
        fg=typer.colors.YELLOW,
        err=True,
    )
    raise typer.Exit(1)


@app.command("mine-pairs")
def mine_pairs_cmd(
    from_time: Optional[str] = typer.Option(
        None,
        "--from",
        help="Start time (ISO-8601). Default: now minus 15 days.",
    ),
    to_time: Optional[str] = typer.Option(
        None,
        "--to",
        help="End time (ISO-8601). Default: now.",
    ),
    count: int = typer.Option(
        20,
        "--count",
        help="Number of distinct v2/v6 pairs to collect.",
    ),
    out_dir: Path = typer.Option(
        Path("results/v2v6-pairs"),
        "--out-dir",
        help="Directory to write pair JSON files.",
    ),
    page_limit: Optional[int] = typer.Option(
        None, "--limit", help="Datadog page size (max 1000)"
    ),
) -> None:
    """Mine Order Create v2/v6 request pairs from Datadog linked by JobID."""
    settings = _load_settings()
    if not from_time or not to_time:
        default_from, default_to = default_training_window()
        from_time = from_time or default_from
        to_time = to_time or default_to

    typer.secho(
        f"Mining up to {count} pairs from {from_time} .. {to_time}",
        fg=typer.colors.BLUE,
        err=True,
    )
    try:
        pairs = mine_pairs(
            settings,
            from_time=from_time,
            to_time=to_time,
            count=count,
            out_dir=out_dir,
            page_limit=page_limit,
        )
    except DatadogError as exc:
        typer.secho(f"Datadog mine-pairs failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    except ValueError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc

    typer.secho(
        f"Wrote {len(pairs)} pairs to {out_dir}",
        fg=typer.colors.GREEN if pairs else typer.colors.YELLOW,
    )
    if len(pairs) < count:
        typer.secho(
            f"Requested {count} pairs but only found {len(pairs)}.",
            fg=typer.colors.YELLOW,
            err=True,
        )
        raise typer.Exit(2 if not pairs else 0)


@app.command("check-pairs")
def check_pairs_cmd(
    pairs_dir: Path = typer.Option(
        Path("results/v2v6-pairs"),
        "--pairs-dir",
        help="Directory of mined pair JSON files.",
    ),
    out: Optional[Path] = typer.Option(
        None,
        "--out",
        help="Report JSON path (default: <pairs-dir>/../v2v6-rule-report.json)",
    ),
) -> None:
    """Diff convert_v2_to_v6 against actual v6 payloads for mined pairs."""
    if not pairs_dir.exists():
        typer.secho(f"Pairs directory not found: {pairs_dir}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    report = run_report(pairs_dir, out_path=out)
    typer.secho(
        f"Pairs: {report['pair_count']} | OK (no rule gaps): {report['ok_count']} | "
        f"with rule gaps: {report['rule_gap_pairs']}",
        fg=typer.colors.CYAN,
        err=True,
    )
    aggregated = report.get("aggregated_rule_gaps") or []
    if aggregated:
        typer.secho("Top rule gaps:", fg=typer.colors.YELLOW, err=True)
        for item in aggregated[:25]:
            typer.secho(
                f"  {item['count']:3d}  {item['key']}",
                fg=typer.colors.YELLOW,
                err=True,
            )
    typer.secho(
        f"Wrote report to {report.get('report_path')}",
        fg=typer.colors.GREEN,
        err=True,
    )
    if report["rule_gap_pairs"]:
        raise typer.Exit(1)


@app.command("mine-validation-pairs")
def mine_validation_pairs_cmd(
    count: int = typer.Option(10, "--count", help="Number of validation pairs."),
    out_dir: Path = typer.Option(
        Path("results/v2v6-pairs-validation"),
        "--out-dir",
        help="Directory to write validation pair JSON files.",
    ),
    train_dir: Path = typer.Option(
        Path("results/v2v6-pairs"),
        "--train-dir",
        help="Training pairs to exclude (holdout validation).",
    ),
    train_days: int = typer.Option(15, "--train-days"),
    validate_days: int = typer.Option(10, "--validate-days"),
    holdout: bool = typer.Option(
        True,
        "--holdout/--prior-window",
        help=(
            "Hold out unused POs from the last train_days (default). "
            "Use --prior-window for days train_days..(train_days+validate_days) "
            "(often empty when indexes retain ~15 days)."
        ),
    ),
) -> None:
    """Mine validation pairs (holdout from training window, or prior window)."""
    settings = _load_settings()
    from error_analysis.order_create.pair_mining import load_pairs

    if holdout:
        from_time, to_time = default_training_window(days=train_days)
    else:
        from_time, to_time = default_validation_window(
            train_days=train_days, validate_days=validate_days
        )

    exclude = {
        str(pair.get("customer_order_number") or "").upper()
        for pair in load_pairs(train_dir)
        if pair.get("customer_order_number")
    }
    typer.secho(
        f"Mining {count} validation pairs from {from_time} .. {to_time} "
        f"(excluding {len(exclude)} training POs, holdout={holdout})",
        fg=typer.colors.BLUE,
        err=True,
    )
    try:
        pairs = mine_pairs(
            settings,
            from_time=from_time,
            to_time=to_time,
            count=count,
            out_dir=out_dir,
            search_text="allowPartialOrder",
            host=None,
            exclude_customers=exclude,
            max_v6_events=800,
        )
    except DatadogError as exc:
        typer.secho(f"Datadog mine failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc

    typer.secho(
        f"Wrote {len(pairs)} validation pairs to {out_dir}",
        fg=typer.colors.GREEN if pairs else typer.colors.YELLOW,
    )
    if not pairs:
        raise typer.Exit(2)


if __name__ == "__main__":
    app()
