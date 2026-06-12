"""
Railway-compatible FastAPI entrypoint for Day09 Multi-Agent Shopping Assistant.

Endpoints:
  GET  /         — Info
  GET  /health   — Liveness probe  (Railway healthcheck)
  GET  /ready    — Readiness probe
  POST /ask      — Ask the multi-agent shopping assistant (X-API-Key required)
"""
from __future__ import annotations

import asyncio
import os
import time
import logging
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Security, Depends, Request, Response
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

# Load .env (for local dev; on Railway vars come from the dashboard)
load_dotenv(Path(__file__).parent / ".env")

# ─────────────────────────────────────────────────────────
# Config from environment
# ─────────────────────────────────────────────────────────
APP_NAME    = os.getenv("APP_NAME", "Shopping Assistant Multi-Agent")
APP_VERSION = os.getenv("APP_VERSION", "1.0.0")
ENVIRONMENT = os.getenv("ENVIRONMENT", "production")
PORT        = int(os.getenv("PORT", "8000"))
AGENT_API_KEY = os.getenv("AGENT_API_KEY", "dev-key-change-me")

ALLOWED_ORIGINS_RAW = os.getenv("ALLOWED_ORIGINS", "*")
ALLOWED_ORIGINS = [o.strip() for o in ALLOWED_ORIGINS_RAW.split(",")]

# ─────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='{"ts":"%(asctime)s","lvl":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────
# Global state
# ─────────────────────────────────────────────────────────
START_TIME   = time.time()
_is_ready    = False
_assistant   = None   # type: ignore  # ShoppingAssistant instance
_req_count   = 0
_err_count   = 0

# ─────────────────────────────────────────────────────────
# Lifespan: initialise ShoppingAssistant in background thread
# so uvicorn can answer /health immediately (non-blocking)
# ─────────────────────────────────────────────────────────
def _init_assistant_sync():
    """Blocking init — runs in thread pool, not on event loop."""
    from app.graph import ShoppingAssistant  # noqa: PLC0415
    return ShoppingAssistant()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _is_ready, _assistant
    logger.info(json.dumps({"event": "startup", "app": APP_NAME, "version": APP_VERSION}))

    # Mark ready immediately so Railway health-check passes
    # while the heavy model download runs in the background
    _is_ready = True
    logger.info(json.dumps({"event": "ready", "note": "assistant loading in background"}))

    loop = asyncio.get_event_loop()
    try:
        # run_in_executor: non-blocking — event loop stays free for /health
        _assistant = await loop.run_in_executor(None, _init_assistant_sync)
        logger.info(json.dumps({"event": "assistant_ready"}))
    except Exception as exc:
        logger.error(json.dumps({"event": "startup_error", "error": str(exc)}))
        _assistant = None

    yield
    _is_ready = False
    logger.info(json.dumps({"event": "shutdown"}))

# ─────────────────────────────────────────────────────────
# App
# ─────────────────────────────────────────────────────────
app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if ENVIRONMENT != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    global _req_count, _err_count
    start = time.time()
    _req_count += 1
    response: Response = await call_next(request)
    # Security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    duration_ms = round((time.time() - start) * 1000, 1)
    logger.info(json.dumps({
        "event": "request",
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "ms": duration_ms,
    }))
    return response

# ─────────────────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────────────────
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    if not api_key or api_key != AGENT_API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API key. Include header: X-API-Key: <key>",
        )
    return api_key

# ─────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────
class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000,
                          description="Câu hỏi gửi cho Shopping Assistant")
    rebuild_index: bool = Field(False, description="Rebuild ChromaDB index (dùng khi thêm policy mới)")

class AskResponse(BaseModel):
    question: str
    answer: str
    route: dict
    timestamp: str

# ─────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────
@app.get("/", tags=["Info"])
def root():
    return {
        "app": APP_NAME,
        "version": APP_VERSION,
        "environment": ENVIRONMENT,
        "endpoints": {
            "ask":   "POST /ask  (requires X-API-Key)",
            "health": "GET /health",
            "ready":  "GET /ready",
            "docs":   "GET /docs (non-production only)",
        },
    }


@app.get("/health", tags=["Operations"])
def health():
    """Liveness probe — Railway/Kubernetes restart container if this fails."""
    return {
        "status": "ok",
        "version": APP_VERSION,
        "environment": ENVIRONMENT,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "total_requests": _req_count,
        "assistant_loaded": _assistant is not None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready", tags=["Operations"])
def ready():
    """Readiness probe — load balancer stops routing here if not ready."""
    if not _is_ready or _assistant is None:
        raise HTTPException(503, "Not ready — assistant not initialised")
    return {"ready": True}


@app.post("/ask", response_model=AskResponse, tags=["Agent"])
async def ask_agent(
    body: AskRequest,
    _key: str = Depends(verify_api_key),
):
    """
    Send a question to the Multi-Agent Shopping Assistant.

    **Authentication:** Include header `X-API-Key: <your-key>`

    The agent routes between:
    - **Policy worker** — shipping fees, return policy, voucher conditions
    - **Data worker**   — order status, customer information
    - **Response worker** — synthesizes final answer
    """
    if _assistant is None:
        raise HTTPException(503, "Assistant not ready. Try again shortly.")

    logger.info(json.dumps({"event": "ask", "q_len": len(body.question)}))

    try:
        result = _assistant.ask(
            question=body.question,
            rebuild_index=body.rebuild_index,
        )
    except Exception as exc:
        global _err_count
        _err_count += 1
        logger.error(json.dumps({"event": "ask_error", "error": str(exc)}))
        raise HTTPException(500, f"Agent error: {exc}")

    return AskResponse(
        question=body.question,
        answer=result.get("final_answer", ""),
        route=result.get("route", {}),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


# ─────────────────────────────────────────────────────────
# Dev runner
# ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=PORT, reload=True)
