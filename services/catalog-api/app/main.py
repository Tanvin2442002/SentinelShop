"""catalog-api FastAPI application.

Run with: uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000
(a factory, so importing this module never needs the env vars; tests rely on that).
"""

import json
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager

import psycopg
import redis
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field

from . import metrics
from .auth import make_token
from .config import Settings, load_settings
from .logging_setup import setup_logging
from .store import Store, make_pool

# Paths polled by probes and Prometheus: logged at DEBUG so they do not flood the logs.
QUIET_PATHS = {"/healthz", "/metrics"}

# The edge sends a 32-hex $request_id. Anything else (missing, too long, odd
# characters) is replaced so a client cannot push junk into every log line.
TRACE_ID_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")


def _trace_id(request: Request) -> str:
    incoming = request.headers.get("x-trace-id", "")
    return incoming if TRACE_ID_RE.match(incoming) else uuid.uuid4().hex


def _client_ip(request: Request) -> str:
    # X-Real-IP is overwritten by the edge, so clients cannot spoof it there.
    # Fallback is the TCP peer (direct calls inside the network, tests).
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip
    return request.client.host if request.client else "-"


class OrderIn(BaseModel):
    # strict=True: the contract says int, so true, "1" and 1.0 are rejected
    # instead of being silently converted to 1.
    product_id: int = Field(gt=0, strict=True)
    quantity: int = Field(ge=1, le=100, strict=True)


class LoginIn(BaseModel):
    # Length caps stop huge bodies reaching bcrypt (which is slow on purpose).
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


# Redis failures can surface as redis-py errors or plain socket errors.
QUEUE_ERRORS = (redis.exceptions.RedisError, OSError)
# psycopg.Error also covers psycopg_pool.PoolTimeout (no free connection / DB down).
DB_ERRORS = (psycopg.Error,)

# Same cap as LoginIn.username, so a huge junk username cannot bloat a log line.
MAX_LOGGED_USER = 64


def _username_for_log(body) -> str:
    """Best-effort username from a body that failed validation. Never the password."""
    if isinstance(body, dict) and "username" in body:
        return str(body["username"])[:MAX_LOGGED_USER]
    return "-"


def _access_level(path: str, status: int) -> int:
    if path in QUIET_PATHS:
        return logging.DEBUG
    if status >= 500:
        return logging.ERROR
    if status in (401, 403):
        return logging.WARNING
    return logging.INFO


def create_app(settings: Settings | None = None, store=None, redis_client=None) -> FastAPI:
    settings = settings or load_settings()
    logger = setup_logging(settings.log_level, settings.log_file)
    store = store or Store(make_pool(settings.database_url))
    # Short timeouts: a dead Redis must make a request fail fast, not hang.
    redis_client = redis_client or redis.Redis.from_url(
        settings.redis_url, socket_timeout=1, socket_connect_timeout=1
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        store.open()
        yield
        store.close()

    app = FastAPI(title="catalog-api", lifespan=lifespan)
    app.state.settings = settings
    app.state.store = store
    app.state.redis = redis_client

    @app.middleware("http")
    async def log_and_measure(request: Request, call_next):
        start = time.perf_counter()
        trace_id = _trace_id(request)
        request.state.trace_id = trace_id
        client_ip = _client_ip(request)

        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "unhandled error",
                extra={"fields": {"trace_id": trace_id, "path": request.url.path}},
            )
            # Generic text only: internals never reach the client.
            response = JSONResponse({"detail": "internal error"}, status_code=500)

        duration = time.perf_counter() - start
        status = response.status_code
        # Route TEMPLATE (e.g. /products/{id}) keeps metric cardinality bounded.
        route = request.scope.get("route")
        route_label = route.path if route is not None else "unmatched"

        metrics.HTTP_REQUESTS.labels(request.method, route_label, str(status)).inc()
        metrics.HTTP_DURATION.labels(request.method, route_label).observe(duration)

        level = _access_level(request.url.path, status)
        logger.log(
            level,
            "request",
            extra={
                "fields": {
                    "trace_id": trace_id,
                    "client_ip": client_ip,
                    "method": request.method,
                    "path": request.url.path,
                    "status": status,
                    "duration_ms": round(duration * 1000, 2),
                }
            },
        )
        response.headers["X-Trace-Id"] = trace_id
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        if request.method == "POST" and request.url.path == "/login":
            # A malformed login (e.g. oversized password) is still a failed
            # login attempt; without this line detection would never see it.
            logger.warning(
                "login failed",
                extra={"fields": {"user": _username_for_log(exc.body),
                                  "client_ip": _client_ip(request),
                                  "trace_id": request.state.trace_id}},
            )
        # Contract: errors are {"detail": "<text>"}, so flatten FastAPI's list.
        parts = []
        for err in exc.errors():
            where = ".".join(str(p) for p in err.get("loc", ()))
            parts.append(f"{where}: {err.get('msg', 'invalid')}")
        return JSONResponse({"detail": "; ".join(parts) or "invalid request"}, status_code=422)

    @app.get("/healthz")
    def healthz():
        # Process alive only; dependencies are checked by /readyz.
        return {"status": "ok"}

    @app.get("/products")
    def list_products():
        return store.list_products()

    # The parameter is named `id` because the route template is part of the
    # metrics contract (route="/products/{id}").
    @app.get("/products/{id}")
    def get_product(id: int):
        product = store.get_product(id)
        if product is None:
            raise HTTPException(status_code=404, detail="product not found")
        return product

    @app.get("/search")
    def search(q: str = Query(max_length=100)):
        return store.search_products(q)

    @app.post("/orders", status_code=201)
    def create_order(order: OrderIn, request: Request):
        trace_id = request.state.trace_id

        def fail(reason: str, detail: str, order_id: int | None = None):
            # Contract: dependency outages are 503 with this ERROR line; a 500
            # from this endpoint must only ever come from chaos (step 8).
            fields = {"trace_id": trace_id, "reason": reason}
            if order_id is not None:
                fields["order_id"] = order_id
            logger.error("order creation failed", extra={"fields": fields})
            raise HTTPException(status_code=503, detail=detail)

        try:
            order_id = store.create_order(order.product_id, order.quantity)
        except DB_ERRORS:
            fail("database unavailable", "order service unavailable, try again later")
        if order_id is None:
            raise HTTPException(status_code=404, detail="product not found")

        # trace_id travels with the message so the worker logs the same id.
        message = json.dumps({"order_id": order_id, "trace_id": trace_id})
        try:
            redis_client.lpush(metrics.QUEUE_KEY, message)
        except QUEUE_ERRORS:
            # The row exists but no worker will ever see it: mark it FAILED
            # so its status is honest, and tell the client to retry later.
            reason = "queue unavailable"
            try:
                store.mark_order_failed(order_id)
            except DB_ERRORS:
                # Both down: the row stays PENDING; the log says so for the RCA.
                reason = "queue unavailable; could not mark order FAILED"
            fail(reason, "order queue unavailable, try again later", order_id)

        metrics.ORDERS_CREATED.inc()
        return {"id": order_id, "status": "PENDING"}

    @app.get("/orders/{id}")
    def get_order(id: int):
        order = store.get_order(id)
        if order is None:
            raise HTTPException(status_code=404, detail="order not found")
        return order

    @app.post("/login")
    def login(credentials: LoginIn, request: Request):
        user = store.check_login(credentials.username, credentials.password)
        if user is None:
            # Detection keys on this line. The password is never logged.
            logger.warning(
                "login failed",
                extra={"fields": {"user": credentials.username,
                                  "client_ip": _client_ip(request),
                                  "trace_id": request.state.trace_id}},
            )
            # Same detail for unknown user and wrong password: no user enumeration.
            raise HTTPException(status_code=401, detail="invalid credentials")
        token = make_token(settings.secret_key, user["username"], settings.token_ttl_seconds)
        return {"token": token, "token_type": "bearer", "expires_in": settings.token_ttl_seconds}

    @app.get("/readyz")
    def readyz():
        failing = []
        try:
            store.ping()
        except Exception:
            failing.append("db")
        try:
            redis_client.ping()
        except Exception:
            failing.append("queue")
        if failing:
            return JSONResponse({"status": "not_ready", "failing": failing}, status_code=503)
        return {"status": "ready"}

    @app.get("/metrics")
    def prometheus_metrics():
        metrics.refresh_queue_depth(redis_client)
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app
