"""catalog-api FastAPI application.

Run with: uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000
(a factory, so importing this module never needs the env vars; tests rely on that).
"""

import logging
import re
import time
import uuid
from contextlib import asynccontextmanager

import redis
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from . import metrics
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

    @app.get("/metrics")
    def prometheus_metrics():
        metrics.refresh_queue_depth(redis_client)
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app
