from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Callable

from backend.config.settings import USE_TRANSFORMER as _USE_TRANSFORMER

if _USE_TRANSFORMER:
    _project_root = Path(__file__).resolve().parent.parent
    _candidate_caches = [
        os.environ.get("HF_HOME"),
        os.environ.get("TRANSFORMERS_CACHE"),
        str(_project_root / ".cache" / "huggingface"),
        str(Path.home() / ".cache" / "huggingface"),
    ]
    for _candidate in _candidate_caches:
        if not _candidate:
            continue
        _model_dir = Path(_candidate) / "hub" / "models--valhalla--distilbart-mnli-12-1"
        if _model_dir.exists():
            os.environ.setdefault("HF_HOME", _candidate)
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            break

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from backend.api.routes import router
from backend.config.settings import (
    RATE_LIMIT_REQUESTS,
    RATE_LIMIT_WINDOW_SECONDS,
    USE_TRANSFORMER,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Link Analyzer", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any, max_requests: int, window_seconds: int) -> None:
        super().__init__(app)
        self._max_requests = max_requests
        self._window = window_seconds
        self._clients: dict[str, list[float]] = {}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        cutoff = now - self._window

        timestamps = self._clients.get(client_ip, [])
        timestamps = [t for t in timestamps if t > cutoff]

        if len(timestamps) >= self._max_requests:
            return Response(
                content='{"detail":"Rate limit exceeded"}',
                status_code=429,
                media_type="application/json",
            )

        timestamps.append(now)
        self._clients[client_ip] = timestamps
        return await call_next(request)


app.add_middleware(
    RateLimitMiddleware,
    max_requests=RATE_LIMIT_REQUESTS,
    window_seconds=RATE_LIMIT_WINDOW_SECONDS,
)

app.include_router(router)


@app.on_event("startup")
async def on_startup() -> None:
    logger.info("Link Analyzer started")
    logger.info(
        "Rate limiting: %d requests per %d seconds",
        RATE_LIMIT_REQUESTS,
        RATE_LIMIT_WINDOW_SECONDS,
    )
    if USE_TRANSFORMER:
        logger.info("Preloading transformer model (USE_TRANSFORMER=true)...")
        from backend.api.routes import _classifier

        loaded = False
        if _classifier._transformer is not None:
            loaded = _classifier._transformer._ensure_loaded()
        logger.info("Transformer model preloaded: %s", loaded)
