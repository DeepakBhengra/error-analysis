from __future__ import annotations

import os
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.responses import Response

from error_analysis.config import Settings, get_settings
from error_analysis.datadog.client import DatadogClient
from error_analysis.datadog.errors import DatadogError
from error_analysis.datadog.fetch_request import (
    fetch_request_records,
    resolve_service_filter,
)
from error_analysis.env_file import upsert_env_values
from error_analysis.logging_config import get_logger, setup_logging
from error_analysis.order_create.curl_builder import (
    OrderCreateCurl,
    OrderCreateCurlError,
    build_order_create_curl_from_records,
)
from error_analysis.error_lookup.client import (
    ErrorLookupError,
    is_two_char_error_code,
    lookup_error_code,
    lookup_error_field,
)
from error_analysis.error_lookup.resolve import resolve_error_code
from error_analysis.order_create.response_check import find_two_char_statuscode_in_sources
from error_analysis.order_create.replay import (
    ReplayResult,
    default_search_window,
    default_time_window,
    run_replay,
    run_replay_from_curl,
)
from error_analysis.order_create.validation_repair import repair_order_create_curl

logger = get_logger("api")


@asynccontextmanager
async def lifespan(_application: FastAPI):
    log_dir = setup_logging()
    logger.info("Error Analysis API starting (log_dir=%s)", log_dir)
    yield
    logger.info("Error Analysis API shutting down")


app = FastAPI(
    title="Error Analysis Order Replay",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next) -> Response:
    """Log API request completion; failures are also written by route handlers."""
    if not request.url.path.startswith("/api"):
        return await call_next(request)

    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000
    if response.status_code >= 500:
        logger.error(
            "%s %s -> %s (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
    elif response.status_code >= 400:
        logger.warning(
            "%s %s -> %s (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
    else:
        logger.info(
            "%s %s -> %s (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Persist unexpected failures and return a stable 500 response.

    ``HTTPException`` is handled by FastAPI's dedicated handler (MRO lookup),
    so this only runs for truly unhandled errors.
    """
    logger.exception(
        "Unhandled exception on %s %s: %s",
        request.method,
        request.url.path,
        exc,
    )
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {exc}"},
    )

Mode = Literal["one_up", "random"]
Target = Literal["uat", "qa"]


class RunRequest(BaseModel):
    text: str = Field(..., min_length=1)
    from_time: str | None = Field(default=None, alias="from")
    to_time: str | None = Field(default=None, alias="to")
    mode: Mode = "one_up"
    index: int = 0
    env: str | None = None
    target: Target = "uat"
    poll_interval: float = 15.0
    timeout: float = 180.0

    model_config = {"populate_by_name": True}


class OrderRequestPreview(BaseModel):
    """Fetch + build editable Order Create curl without posting."""

    text: str = Field(..., min_length=1)
    from_time: str | None = Field(default=None, alias="from")
    to_time: str | None = Field(default=None, alias="to")
    index: int = 0
    env: str | None = None
    target: Target = "uat"

    model_config = {"populate_by_name": True}


class OrderCurlRequest(BaseModel):
    """Authenticated curl generation from a customer order number only."""

    customer_order_number: str = Field(..., min_length=1, alias="customerOrderNumber")

    model_config = {"populate_by_name": True}


class ResubmitRequest(BaseModel):
    curl: str = Field(..., min_length=1)
    mode: Mode = "one_up"
    env: str | None = None
    poll_interval: float = 15.0
    timeout: float = 180.0


class ErrorLookupRequest(BaseModel):
    error_code: str = Field(..., min_length=1, max_length=8)


class SettingsUpdateRequest(BaseModel):
    """Partial settings update. Empty secret fields leave existing values unchanged."""

    dd_api_key: str | None = None
    dd_app_key: str | None = None
    dd_access_token: str | None = None
    dd_site: str | None = None
    order_create_username: str | None = None
    order_create_password: str | None = None
    order_create_cookie: str | None = None
    default_target: Target | None = None
    default_mode: Mode | None = None


def _normalize_target(value: str) -> Target:
    cleaned = (value or "uat").strip().lower()
    return "qa" if cleaned == "qa" else "uat"


def _normalize_mode(value: str) -> Mode:
    cleaned = (value or "one_up").strip().lower()
    return "random" if cleaned == "random" else "one_up"


def _settings_response(settings: Settings) -> dict[str, Any]:
    dd_api_configured = bool(settings.dd_api_key.strip())
    dd_app_configured = bool(settings.dd_app_key.strip())
    dd_access_token_configured = bool(settings.dd_access_token.strip())
    password_configured = bool(settings.order_create_password.strip())
    cookie_configured = bool(settings.order_create_cookie.strip())
    return {
        "dd_api_key": "",
        "dd_app_key": "",
        "dd_access_token": "",
        "dd_site": settings.dd_site,
        "dd_api_key_configured": dd_api_configured,
        "dd_app_key_configured": dd_app_configured,
        "dd_access_token_configured": dd_access_token_configured,
        "dd_auth_mode": "access_token" if settings.uses_access_token else "api_keys",
        "order_create_username": settings.order_create_username,
        "order_create_password": "",
        "order_create_cookie": "",
        "order_create_password_configured": password_configured,
        "order_create_cookie_configured": cookie_configured,
        "default_target": _normalize_target(settings.default_order_create_target),
        "default_mode": _normalize_mode(settings.default_replay_mode),
    }


def _load_settings() -> Settings:
    try:
        return get_settings()
    except Exception as exc:
        logger.exception("Configuration error while loading settings")
        raise HTTPException(
            status_code=500,
            detail=f"Configuration error: {exc}. Copy .env.example to .env.",
        ) from exc


def _require_order_curl_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    """Validate inbound X-API-Key for the order-curl endpoint."""
    settings = _load_settings()
    expected = settings.order_curl_api_key.strip()
    provided = (x_api_key or "").strip()
    if not expected or not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


def _banner_message(
    result: ReplayResult,
    *,
    statuscode: str | None = None,
) -> str:
    summary = result.summary or {}
    impulse = summary.get("globalorderid") or ""
    if result.outcome == "SUCCESS":
        msg = summary.get("responsemessage") or "SUCCESS"
        if impulse:
            return f"Success report: {msg}. Impulse Order Number: {impulse}."
        return f"Success report: {msg}."
    if result.outcome == "FAILED":
        status = summary.get("responsestatus") or "FAILED"
        code = statuscode if statuscode is not None else (summary.get("statuscode") or "")
        msg = summary.get("responsemessage") or "FAILED"
        return f"Failure: status={status}, Error Code={code}, Error Message={msg}."
    if result.outcome == "TIMEOUT":
        return summary.get("message") or "Timed out waiting for ResponseLogPayload."
    return (
        f"Unknown outcome. statuscode={summary.get('statuscode', '')}, "
        f"message={summary.get('responsemessage', '')}."
    )


def _enrich_failed_statuscode(
    settings: Settings,
    *,
    statuscode: str,
    responsemessage: str,
    records: list[dict[str, Any]] | None = None,
    response_payload: dict[str, Any] | None = None,
    http_body: Any = None,
) -> tuple[str, dict[str, Any]]:
    """Map non-two-char FAILED statuscode for the UI.

    Order of preference:
    1. Two-char ``<tns:statuscode>`` / v2 XML statuscode from Order Create v2 response
    2. COBOL error_field lookup using responsemessage

    Returns (possibly mapped statuscode, extra response fields).
    Lookup failures are swallowed so replay results still return.
    """
    extras: dict[str, Any] = {}
    if is_two_char_error_code(statuscode):
        return statuscode, extras

    extras["originalStatuscode"] = statuscode

    mapped_from_v2 = find_two_char_statuscode_in_sources(
        records=records,
        response_payload=response_payload,
        http_body=http_body,
    )
    if mapped_from_v2:
        extras["mappedFromV2Statuscode"] = mapped_from_v2
        return mapped_from_v2, extras

    field = responsemessage.strip()
    if not field:
        return statuscode, extras

    extras["mappedFromErrorField"] = field
    try:
        mapped = lookup_error_field(settings, field)
        code = str(mapped.get("error_code") or "").strip()
        if code:
            return code, extras
    except ErrorLookupError as exc:
        logger.warning("FAILED statuscode enrichment lookup failed: %s", exc)
        extras["lookupError"] = str(exc)
    return statuscode, extras


def _api_response(
    result: ReplayResult,
    *,
    settings: Settings | None = None,
    source_text: str | None = None,
) -> dict[str, Any]:
    summary = result.summary or {}
    check = result.check
    responsestatus = summary.get("responsestatus") or (
        check.responsestatus if check else ""
    )
    statuscode = summary.get("statuscode") or (check.statuscode if check else "")
    responsemessage = summary.get("responsemessage") or (
        check.responsemessage if check else ""
    )
    globalorderid = summary.get("globalorderid") or (
        check.globalorderid if check else ""
    )

    customer_order_number = result.customer_order_number
    if check is not None and check.customer_order_number.strip():
        customer_order_number = check.customer_order_number.strip()

    response_payload = summary.get("ResponseLogPayload")
    if response_payload is None and check is not None:
        response_payload = check.response_payload

    extras: dict[str, Any] = {}
    if result.outcome == "FAILED" and settings is not None:
        statuscode, extras = _enrich_failed_statuscode(
            settings,
            statuscode=statuscode,
            responsemessage=responsemessage,
            records=result.records,
            response_payload=response_payload if isinstance(response_payload, dict) else None,
            http_body=result.http_body,
        )

    message = _banner_message(result, statuscode=statuscode)
    curl_text = result.curl
    curl_repaired = False
    repaired_fields: list[str] = []
    unresolved_fields: list[str] = []
    repair_message = ""

    if settings is not None and result.http_body is not None and curl_text.strip():
        repair = repair_order_create_curl(
            curl_text,
            result.http_body,
            username=settings.order_create_username or "",
            password=settings.order_create_password or "",
        )
        if repair.repaired:
            curl_text = repair.curl
            curl_repaired = True
            repaired_fields = list(repair.repaired_fields)
            unresolved_fields = list(repair.unresolved_fields)
            repair_message = repair.message
            if repair_message:
                message = f"{message} {repair_message}".strip()
        elif repair.unresolved_fields:
            unresolved_fields = list(repair.unresolved_fields)
            repair_message = repair.message
            if repair_message:
                message = f"{message} {repair_message}".strip()

    payload: dict[str, Any] = {
        "outcome": result.outcome,
        "responsestatus": responsestatus,
        "statuscode": statuscode,
        "responsemessage": responsemessage,
        "globalorderid": globalorderid,
        "customerOrderNumber": customer_order_number,
        "originalCustomerOrderNumber": result.original_order_number,
        "sourceSearchText": source_text or summary.get("sourceSearchText"),
        "http_status": result.http_status,
        "http_body": result.http_body,
        "message": message,
        "curl": curl_text,
        "curlRepaired": curl_repaired,
        "repairedFields": repaired_fields,
        "unresolvedFields": unresolved_fields,
        "repairMessage": repair_message,
        "result": summary,
    }
    payload.update(extras)
    return payload


@app.get("/api/health")
def health() -> dict[str, Any]:
    settings = _load_settings()
    try:
        with DatadogClient(settings) as client:
            valid = client.validate_credentials().get("valid", False)
    except Exception as exc:
        logger.warning("Health check Datadog validation failed: %s", exc)
        return {"ok": False, "datadog": False, "detail": str(exc)}
    return {"ok": True, "datadog": bool(valid)}


@app.get("/api/settings")
def get_app_settings() -> dict[str, Any]:
    """Return settings for the UI; secrets are masked."""
    return _settings_response(_load_settings())


@app.put("/api/settings")
def update_app_settings(payload: SettingsUpdateRequest) -> dict[str, Any]:
    """Persist settings to ``.env``. Empty secret fields leave existing values unchanged."""
    updates: dict[str, str] = {}

    if payload.dd_api_key is not None and payload.dd_api_key.strip():
        updates["DD_API_KEY"] = payload.dd_api_key.strip()
    if payload.dd_app_key is not None and payload.dd_app_key.strip():
        updates["DD_APP_KEY"] = payload.dd_app_key.strip()
    if payload.dd_access_token is not None and payload.dd_access_token.strip():
        updates["DD_ACCESS_TOKEN"] = payload.dd_access_token.strip()
    if payload.dd_site is not None:
        site = payload.dd_site.strip()
        if site:
            updates["DD_SITE"] = site
    if payload.order_create_username is not None:
        updates["ORDER_CREATE_USERNAME"] = payload.order_create_username.strip()
    if payload.order_create_password is not None and payload.order_create_password.strip():
        updates["ORDER_CREATE_PASSWORD"] = payload.order_create_password.strip()
    if payload.order_create_cookie is not None and payload.order_create_cookie.strip():
        updates["ORDER_CREATE_COOKIE"] = payload.order_create_cookie.strip()
    if payload.default_target is not None:
        updates["DEFAULT_ORDER_CREATE_TARGET"] = _normalize_target(payload.default_target)
    if payload.default_mode is not None:
        updates["DEFAULT_REPLAY_MODE"] = _normalize_mode(payload.default_mode)

    if updates:
        try:
            upsert_env_values(updates)
        except OSError as exc:
            logger.exception("Failed to write settings to .env")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to write .env: {exc}",
            ) from exc

    # Clear process env overrides for keys we wrote so env_file wins on reload.
    for key in updates:
        os.environ.pop(key, None)

    return _settings_response(_load_settings())


def _preview_message(built: OrderCreateCurl, *, text: str) -> str:
    order_number = ""
    if isinstance(built.body.get("customerOrderNumber"), str):
        order_number = built.body["customerOrderNumber"].strip()
    if built.source == "v2-converted":
        return (
            f"v6 request ready (converted from Order Create v2) "
            f"for {order_number or text!r}. Edit the curl, then Re-Submit."
        )
    return (
        f"v6 request ready (from Order Create v6 log) "
        f"for {order_number or text!r}. Edit the curl, then Re-Submit."
    )


@app.post("/api/order-request")
def order_request_preview(payload: OrderRequestPreview) -> dict[str, Any]:
    """Search Datadog and return an editable Order Create v6 curl (no POST)."""
    settings = _load_settings()
    text = payload.text.strip()
    search_from = payload.from_time
    search_to = payload.to_time
    if not search_from or not search_to:
        search_from, search_to = default_search_window(30)

    if not settings.order_create_username.strip():
        raise HTTPException(
            status_code=400,
            detail="ORDER_CREATE_USERNAME is required in .env for order-request preview.",
        )

    service = resolve_service_filter(settings)
    try:
        with DatadogClient(settings) as client:
            fetched = fetch_request_records(
                client,
                settings,
                from_time=search_from,
                to_time=search_to,
                text=text,
                env=payload.env,
                service=service,
            )
    except ValueError as exc:
        logger.warning("order-request invalid input: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DatadogError as exc:
        logger.error("order-request Datadog fetch failed for %r: %s", text, exc)
        raise HTTPException(
            status_code=502, detail=f"Datadog fetch failed: {exc}"
        ) from exc

    if not fetched.records:
        logger.warning(
            "order-request found no records for %r (query=%s)", text, fetched.query
        )
        raise HTTPException(
            status_code=404,
            detail=(
                f"No Order Create request/response records found for {text!r}."
                f" Query used: {fetched.query}"
            ),
        )

    try:
        built = build_order_create_curl_from_records(
            fetched.records,
            username=settings.order_create_username,
            password=settings.order_create_password,
            redact_password=False,
            index=payload.index,
            cookie=settings.order_create_cookie or None,
            target=payload.target,
        )
    except OrderCreateCurlError as exc:
        logger.warning("order-request curl build failed for %r: %s", text, exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    order_number = ""
    if isinstance(built.body.get("customerOrderNumber"), str):
        order_number = built.body["customerOrderNumber"].strip()

    return {
        "outcome": "READY",
        "message": _preview_message(built, text=text),
        "curl": built.curl,
        "body": built.body,
        "source": built.source,
        "customerOrderNumber": order_number,
        "originalCustomerOrderNumber": order_number,
        "sourceSearchText": text,
        "url": built.url,
        "query": fetched.query,
        "recordCount": len(fetched.records),
        "target": payload.target,
    }


@app.post("/api/v1/order-curl", response_class=PlainTextResponse)
def order_curl(
    payload: OrderCurlRequest,
    _: None = Depends(_require_order_curl_api_key),
) -> str:
    """Return the same complete generated curl displayed by the UI."""
    settings = _load_settings()
    text = payload.customer_order_number.strip()
    if not text:
        raise HTTPException(
            status_code=422,
            detail="customerOrderNumber is required.",
        )

    search_from, search_to = default_search_window(30)
    target = _normalize_target(settings.default_order_create_target)

    if not settings.order_create_username.strip():
        raise HTTPException(
            status_code=400,
            detail="ORDER_CREATE_USERNAME is required in .env for order-curl.",
        )

    service = resolve_service_filter(settings)
    try:
        with DatadogClient(settings) as client:
            fetched = fetch_request_records(
                client,
                settings,
                from_time=search_from,
                to_time=search_to,
                text=text,
                env=None,
                service=service,
            )
    except ValueError as exc:
        logger.warning("order-curl invalid input: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DatadogError as exc:
        logger.error("order-curl Datadog fetch failed for %r: %s", text, exc)
        raise HTTPException(
            status_code=502, detail=f"Datadog fetch failed: {exc}"
        ) from exc

    if not fetched.records:
        logger.warning(
            "order-curl found no records for %r (query=%s)", text, fetched.query
        )
        raise HTTPException(
            status_code=404,
            detail=(
                f"No Order Create request/response records found for {text!r}."
                f" Query used: {fetched.query}"
            ),
        )

    try:
        built = build_order_create_curl_from_records(
            fetched.records,
            username=settings.order_create_username,
            password=settings.order_create_password,
            redact_password=False,
            index=0,
            cookie=settings.order_create_cookie or None,
            target=target,
        )
    except OrderCreateCurlError as exc:
        logger.warning("order-curl curl build failed for %r: %s", text, exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return built.curl


@app.post("/api/run")
def run_order(payload: RunRequest) -> dict[str, Any]:
    settings = _load_settings()
    text = payload.text.strip()
    search_from = payload.from_time
    search_to = payload.to_time
    if not search_from or not search_to:
        search_from, search_to = default_search_window(30)

    service = resolve_service_filter(settings)
    try:
        with DatadogClient(settings) as client:
            fetched = fetch_request_records(
                client,
                settings,
                from_time=search_from,
                to_time=search_to,
                text=text,
                env=payload.env,
                service=service,
            )
    except ValueError as exc:
        logger.warning("run invalid input: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DatadogError as exc:
        logger.error("run Datadog fetch failed for %r: %s", text, exc)
        raise HTTPException(status_code=502, detail=f"Datadog fetch failed: {exc}") from exc

    if not fetched.records:
        logger.warning("run found no records for %r (query=%s)", text, fetched.query)
        raise HTTPException(
            status_code=404,
            detail=(
                f"No Order Create request/response records found for {text!r}."
                f" Query used: {fetched.query}"
            ),
        )

    poll_from, poll_to = default_time_window()
    try:
        result = run_replay(
            settings,
            fetched.records,
            index=payload.index,
            use_random=payload.mode == "random",
            from_time=poll_from,
            to_time=poll_to,
            poll_interval=payload.poll_interval,
            timeout=payload.timeout,
            env=payload.env,
            out_dir=None,
            source_search_text=text,
            target=payload.target,
        )
    except OrderCreateCurlError as exc:
        logger.warning("run curl/replay setup failed for %r: %s", text, exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("run replay failed for %r", text)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if result.outcome == "FAILED":
        logger.warning(
            "run completed with FAILED for %r (statuscode=%s)",
            text,
            (result.summary or {}).get("statuscode"),
        )
    elif result.outcome == "TIMEOUT":
        logger.error("run timed out waiting for response logs for %r", text)
    else:
        logger.info("run completed with %s for %r", result.outcome, text)

    return _api_response(result, settings=settings, source_text=text)


@app.post("/api/error-lookup")
def error_lookup(payload: ErrorLookupRequest) -> dict[str, Any]:
    settings = _load_settings()
    try:
        return lookup_error_code(settings, payload.error_code)
    except ErrorLookupError as exc:
        logger.error("error-lookup failed for %r: %s", payload.error_code, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("error-lookup unexpected failure for %r", payload.error_code)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/resolve-error")
def resolve_error(payload: ErrorLookupRequest) -> dict[str, Any]:
    """Lookup error code, persist as ``{CODE} Business Logic.json``, or return cache."""
    settings = _load_settings()
    try:
        return resolve_error_code(settings, payload.error_code)
    except ErrorLookupError as exc:
        detail = str(exc)
        if "error_code is required" in detail:
            logger.warning("resolve-error bad request: %s", detail)
            raise HTTPException(status_code=400, detail=detail) from exc
        logger.error("resolve-error failed for %r: %s", payload.error_code, exc)
        raise HTTPException(status_code=502, detail=detail) from exc
    except Exception as exc:
        logger.exception("resolve-error unexpected failure for %r", payload.error_code)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/resubmit")
def resubmit_curl(payload: ResubmitRequest) -> dict[str, Any]:
    settings = _load_settings()
    poll_from, poll_to = default_time_window()
    try:
        result = run_replay_from_curl(
            settings,
            payload.curl,
            use_random=payload.mode == "random",
            from_time=poll_from,
            to_time=poll_to,
            poll_interval=payload.poll_interval,
            timeout=payload.timeout,
            env=payload.env,
            # Keep last resubmit artifacts (body/curl/logs/result) for diagnosis.
            out_dir=Path("results/last-resubmit"),
        )
    except OrderCreateCurlError as exc:
        logger.warning("resubmit curl parse/setup failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("resubmit replay failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if result.outcome in {"FAILED", "TIMEOUT"}:
        logger.warning("resubmit completed with %s", result.outcome)
    else:
        logger.info("resubmit completed with %s", result.outcome)

    return _api_response(result, settings=settings)


def _resolve_web_dist() -> Path | None:
    """Locate the Vite production build (``web/dist``) when present."""
    env = (os.environ.get("ERROR_ANALYSIS_WEB_DIST") or "").strip()
    candidates: list[Path] = []
    if env:
        candidates.append(Path(env))
    candidates.append(Path.cwd() / "web" / "dist")
    # src/error_analysis/api.py → project root
    candidates.append(Path(__file__).resolve().parents[2] / "web" / "dist")
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if (resolved / "index.html").is_file():
            return resolved
    return None


def _mount_web_ui(application: FastAPI) -> None:
    dist = _resolve_web_dist()
    if dist is None:
        return

    assets = dist / "assets"
    if assets.is_dir():
        application.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @application.get("/")
    def spa_index() -> FileResponse:
        return FileResponse(dist / "index.html")

    @application.get("/{full_path:path}")
    def spa_static_or_index(full_path: str) -> FileResponse:
        # API routes are registered earlier and take precedence; this only
        # catches leftover browser paths (favicon, deep links, etc.).
        if full_path.startswith("api/") or full_path == "api":
            raise HTTPException(status_code=404, detail="Not found")
        candidate = (dist / full_path).resolve()
        try:
            candidate.relative_to(dist.resolve())
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Not found") from exc
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")


_mount_web_ui(app)


def main() -> None:
    import uvicorn

    log_dir = setup_logging()
    logger.info("Launching Error Analysis API (log_dir=%s)", log_dir)

    # Prefer 8010 so this does not collide with other local tools on 8000
    # (e.g. Legacy COBOL Error Scanner API).
    # Dev: set ERROR_ANALYSIS_RELOAD=1 (start-dev.ps1). Prod one-click: leave unset.
    reload = os.environ.get("ERROR_ANALYSIS_RELOAD", "0").lower() in {
        "1",
        "true",
        "yes",
    }
    uvicorn.run(
        "error_analysis.api:app",
        host="127.0.0.1",
        port=8010,
        reload=reload,
    )


if __name__ == "__main__":
    main()
