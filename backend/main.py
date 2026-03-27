import time
import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from app.api import router as api_router
from app.core.config import settings
from app.core.logging import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info(f"Starting {settings.app_name}")
    timeout = httpx.Timeout(60.0, connect=10.0)
    limits = httpx.Limits(max_connections=32, max_keepalive_connections=16)
    async with httpx.AsyncClient(timeout=timeout, limits=limits, follow_redirects=True) as client:
        app.state.http_client = client
        yield
    logger.info("Shutting down")


app = FastAPI(
    title=settings.app_name,
    description="ML-платформа для анализа и прогнозирования движения акций",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    started = time.perf_counter()
    method = request.method
    path = request.url.path
    client_ip = request.client.host if request.client else "-"
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = round((time.perf_counter() - started) * 1000.0, 2)
        logger.bind(
            request_id=request_id,
            method=method,
            path=path,
            client_ip=client_ip,
            duration_ms=duration_ms,
        ).exception("HTTP request failed")
        raise

    duration_ms = round((time.perf_counter() - started) * 1000.0, 2)
    status_code = response.status_code
    log = logger.warning if status_code >= 500 else logger.info
    log(
        "HTTP {method} {path} -> {status_code} ({duration_ms} ms) [request_id={request_id}, client_ip={client_ip}]",
        method=method,
        path=path,
        status_code=status_code,
        duration_ms=duration_ms,
        request_id=request_id,
        client_ip=client_ip,
    )
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = getattr(request.state, "request_id", "unknown")
    logger.warning(
        "HTTPException {status_code} on {path} [request_id={request_id}]: {detail}",
        status_code=exc.status_code,
        path=request.url.path,
        request_id=request_id,
        detail=str(exc.detail),
    )
    code = f"http_{exc.status_code}"
    payload = {
        "error": {
            "code": code,
            "message": str(exc.detail),
            "request_id": request_id,
        }
    }
    return JSONResponse(status_code=exc.status_code, content=payload)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    logger.exception("Unhandled error (request_id={}): {}", request_id, exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "Internal server error",
                "request_id": request_id,
            }
        },
    )

app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    return {"status": "ok", "app": settings.app_name}
