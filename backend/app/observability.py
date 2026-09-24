"""Logging, metrics and request context.

- JSON logs (one object per line) carrying `request_id`, `conversation_id` and
  `customer_id` from context variables, so a single turn can be traced across
  log lines and pods.
- Prometheus metrics exposed at `/metrics`. Run one server process per
  container (scale with replicas) so each scrape target is one process.
- A pure-ASGI middleware that assigns/propagates `X-Request-ID`, enforces the
  request body limit, and records HTTP latency — pure ASGI (not
  BaseHTTPMiddleware) so SSE responses stream untouched.
- Optional Sentry when `SENTRY_DSN` is set.
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
import time
import uuid

from prometheus_client import Counter, Gauge, Histogram

from app.config import get_settings

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
conversation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "conversation_id", default=""
)
customer_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("customer_id", default="")

# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

HTTP_REQUESTS = Counter(
    "http_requests_total", "HTTP requests", ["method", "route", "status"]
)
HTTP_LATENCY = Histogram(
    "http_request_duration_seconds",
    "Time to response start (SSE: time to first byte)",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
TURNS = Counter("agent_turns_total", "Agent turns by outcome", ["outcome"])
TURN_LATENCY = Histogram(
    "agent_turn_duration_seconds",
    "Full agent turn duration",
    buckets=(0.5, 1, 2, 4, 8, 15, 30, 60, 120),
)
TURNS_IN_FLIGHT = Gauge("agent_turns_in_flight", "Agent turns running in this process")
LLM_TOKENS = Counter("llm_tokens_total", "LLM tokens", ["direction"])
TOOL_CALLS = Counter("agent_tool_calls_total", "Tool calls", ["tool"])
REFUND_DECISIONS = Counter("refund_decisions_total", "Refund decisions", ["decision"])
INJECTION_FLAGS = Counter("injection_flags_total", "Messages flagged as injection attempts")
REJECTIONS = Counter(
    "chat_rejections_total", "Chat requests rejected before a turn", ["reason"]
)
SSE_STREAMS = Gauge("sse_streams_open", "Open SSE streams", ["kind"])

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, var in (
            ("request_id", request_id_var),
            ("conversation_id", conversation_id_var),
            ("customer_id", customer_id_var),
        ):
            value = var.get()
            if value:
                out[key] = value
        extra = getattr(record, "extra_fields", None)
        if extra:
            out.update(extra)
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str)


def configure_logging() -> None:
    settings = get_settings()
    handler = logging.StreamHandler(sys.stdout)
    if settings.log_json:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(settings.log_level.upper())
    # Uvicorn's access log duplicates our structured request log.
    logging.getLogger("uvicorn.access").disabled = True


def configure_sentry() -> None:
    settings = get_settings()
    if not settings.sentry_dsn:
        return
    import sentry_sdk

    sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.env, traces_sample_rate=0.05)


def log_event(logger: logging.Logger, msg: str, level: int = logging.INFO, **fields) -> None:
    logger.log(level, msg, extra={"extra_fields": fields})


# ---------------------------------------------------------------------------
# ASGI middleware
# ---------------------------------------------------------------------------

_access_log = logging.getLogger("app.access")


class RequestContextMiddleware:
    """Request id, body-size limit, access log and HTTP metrics."""

    def __init__(self, app, max_body_bytes: int):
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        headers = dict(scope.get("headers") or [])
        rid = headers.get(b"x-request-id", b"").decode()[:64] or uuid.uuid4().hex
        token = request_id_var.set(rid)
        start = time.perf_counter()
        status_holder = {"status": 500}
        method = scope.get("method", "")

        declared = headers.get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > self.max_body_bytes:
            await _send_json(send, 413, {"detail": "request body too large"}, rid)
            request_id_var.reset(token)
            return

        received = 0

        async def limited_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_body_bytes:
                    raise _BodyTooLarge()
            return message

        recorded = False

        async def send_wrapper(message):
            nonlocal recorded
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                message.setdefault("headers", [])
                message["headers"] = list(message["headers"]) + [
                    (b"x-request-id", rid.encode())
                ]
                if not recorded:
                    recorded = True
                    route = _route_template(scope)
                    HTTP_LATENCY.labels(method, route).observe(time.perf_counter() - start)
                    HTTP_REQUESTS.labels(method, route, str(message["status"])).inc()
            await send(message)

        try:
            await self.app(scope, limited_receive, send_wrapper)
        except _BodyTooLarge:
            await _send_json(send, 413, {"detail": "request body too large"}, rid)
            status_holder["status"] = 413
        finally:
            path = scope.get("path", "")
            if path not in ("/metrics", "/api/health/live", "/api/health/ready"):
                log_event(
                    _access_log,
                    "request",
                    method=method,
                    path=path,
                    status=status_holder["status"],
                    duration_ms=round((time.perf_counter() - start) * 1000, 1),
                )
            request_id_var.reset(token)


class _BodyTooLarge(Exception):
    pass


def _route_template(scope) -> str:
    route = scope.get("route")
    path = getattr(route, "path", None)
    return path or "unmatched"


async def _send_json(send, status: int, body: dict, rid: str) -> None:
    payload = json.dumps(body).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode()),
                (b"x-request-id", rid.encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": payload})
